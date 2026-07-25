use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter};

use audiodsp::ofdm::{
    encode_packets_sized, max_packet_payload, pack_payload, packed_chunk_count, Modulation,
    OfdmConfig,
};

use super::capture::start_capture;
use super::player::OutputPlayer;
use super::proto;
use super::sendplan::{self, AckStep, CtrlOutcome, RetryStep};
use super::session::{listen_once, wait_ctrl_on, CtrlWait};

const LISTEN_WINDOW: Duration = Duration::from_millis(900);
const LISTEN_TAIL_SECONDS: f32 = 2.5;
const MAX_PACKET_RETRIES: usize = 3;
const MAX_ROUNDS: usize = 6;
const MAX_FULL_REPLAYS: usize = 1;
const ACK_WAIT: Duration = Duration::from_secs(12);

pub fn run_send_file(
    app: &AppHandle,
    stop: Arc<AtomicBool>,
    name: &str,
    content: &[u8],
    key: [u8; 32],
) -> Result<String, String> {
    let safe = proto::sanitize_filename(name);
    let mut hasher = Sha256::new();
    hasher.update(content);
    let digest: [u8; 32] = hasher.finalize().into();
    let _ = app.emit(
        "modem-status",
        format!("Шифрую и готовлю файл «{safe}» к передаче..."),
    );
    let envelope = proto::encode_file(&safe, &digest, content);
    run_send(app, stop, &envelope, Some(&key))
}

pub fn run_send_msg(app: &AppHandle, stop: Arc<AtomicBool>, body: &[u8]) -> Result<String, String> {
    let envelope = proto::encode_msg(body);
    run_send(app, stop, &envelope, None)
}

pub fn run_send(
    app: &AppHandle,
    stop: Arc<AtomicBool>,
    envelope: &[u8],
    key: Option<&[u8; 32]>,
) -> Result<String, String> {
    let mut cfg = OfdmConfig::default_48k();
    cfg.headroom = audiodsp::PLAYBACK_GAIN.clamp(0.05, 1.0);

    let mut sizing_cfg = cfg.clone();
    sizing_cfg.modulation = Modulation::Bpsk;
    let chunk_max = max_packet_payload(&sizing_cfg).max(1);

    let packed = pack_payload(envelope, key);
    let total = packed_chunk_count(packed.len(), &sizing_cfg);
    if !sendplan::within_limit(total) {
        return Err("Данные слишком велики для передачи звуком.".to_string());
    }

    let out = OutputPlayer::open()?;
    let cap = start_capture()?;
    let mut missing: Vec<u16> = Vec::new();

    let mut modulation = Modulation::Bpsk;
    for seq in 0..total {
        if stop.load(Ordering::SeqCst) {
            return Ok("Передача остановлена.".to_string());
        }
        let mut retry = sendplan::PacketRetry::new(MAX_PACKET_RETRIES);
        loop {
            let mut pkt_cfg = cfg.clone();
            pkt_cfg.modulation = modulation;
            let _ = app.emit(
                "modem-status",
                format!("Передаю пакет {}/{total} ({modulation:?})...", seq + 1),
            );
            let wave = encode_packets_sized(&packed, &[seq], total, chunk_max, &pkt_cfg);
            out.play(&wave, cfg.fs, &stop)?;
            if stop.load(Ordering::SeqCst) {
                return Ok("Передача остановлена.".to_string());
            }
            let rate_ok = match listen_once(&cap, &cfg, LISTEN_WINDOW, LISTEN_TAIL_SECONDS) {
                Some(CtrlWait::Rate {
                    seq: s,
                    ok,
                    modulation: m,
                    snr_db,
                }) if s as usize == seq => {
                    modulation = m;
                    let _ = app.emit(
                        "modem-status",
                        format!("Приёмник: SNR {snr_db:.1} дБ, модуляция {m:?}"),
                    );
                    Some(ok)
                }
                _ => None,
            };
            match retry.step(rate_ok) {
                RetryStep::Done | RetryStep::NoResponse => break,
                RetryStep::Retry => continue,
                RetryStep::GiveUp => {
                    missing.push(seq as u16);
                    break;
                }
            }
        }
    }

    let mut ack = sendplan::AckLoop::new(total, MAX_FULL_REPLAYS, missing);
    for _round in 1..=MAX_ROUNDS {
        if stop.load(Ordering::SeqCst) {
            return Ok("Передача остановлена.".to_string());
        }
        if let Some(t) = ack.targets() {
            let mut safe_cfg = cfg.clone();
            safe_cfg.modulation = Modulation::Bpsk;
            let seqs: Vec<usize> = t.iter().map(|&s| s as usize).collect();
            let _ = app.emit(
                "modem-status",
                format!("Досылаю {} из {total} пакетов...", seqs.len()),
            );
            let wave = encode_packets_sized(&packed, &seqs, total, chunk_max, &safe_cfg);
            out.play(&wave, cfg.fs, &stop)?;
        }
        let _ = app.emit("modem-status", "Жду подтверждение приёма...".to_string());
        let outcome = match wait_ctrl_on(app, &stop, &cfg, &cap, ACK_WAIT) {
            CtrlWait::Ack(t) => CtrlOutcome::Ack(t as usize),
            CtrlWait::Nak(t, miss) => CtrlOutcome::Nak(t as usize, miss),
            CtrlWait::Rate { .. } => CtrlOutcome::Rate,
            CtrlWait::Timeout => CtrlOutcome::Timeout,
            CtrlWait::Stopped => CtrlOutcome::Stopped,
        };
        let was_timeout = matches!(outcome, CtrlOutcome::Timeout);
        let had_targets = ack.targets().is_some();
        match ack.react(outcome) {
            AckStep::Delivered => {
                return Ok("Доставлено: приёмник подтвердил получение.".to_string());
            }
            AckStep::GiveUp => {
                return Ok("Передано, но подтверждение не получено.".to_string());
            }
            AckStep::Stopped => return Ok("Передача остановлена.".to_string()),
            AckStep::Retransmit => {
                if was_timeout && !had_targets && ack.targets().is_some() {
                    let _ = app.emit(
                        "modem-status",
                        "Ответа нет — повторяю передачу полностью...".to_string(),
                    );
                }
            }
        }
    }
    Ok("Передано, подтверждение после повторов не получено.".to_string())
}
