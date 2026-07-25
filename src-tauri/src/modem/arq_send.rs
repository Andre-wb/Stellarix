use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tauri::{AppHandle, Emitter};

use audiodsp::ofdm::{
    encode_packets_sized, max_packet_payload, pack_payload, packed_chunk_count, Modulation,
    OfdmConfig,
};

use super::capture::start_capture;
use super::player::OutputPlayer;
use super::session::{listen_once, wait_ctrl_on, CtrlWait};

const LISTEN_WINDOW: Duration = Duration::from_millis(900);
const LISTEN_TAIL_SECONDS: f32 = 2.5;
const MAX_PACKET_RETRIES: usize = 3;
const MAX_ROUNDS: usize = 6;
const MAX_FULL_REPLAYS: usize = 1;
const ACK_WAIT: Duration = Duration::from_secs(12);

pub fn run_send(app: &AppHandle, stop: Arc<AtomicBool>, envelope: &[u8]) -> Result<String, String> {
    let mut cfg = OfdmConfig::default_48k();
    cfg.headroom = audiodsp::PLAYBACK_GAIN.clamp(0.05, 1.0);

    let mut sizing_cfg = cfg.clone();
    sizing_cfg.modulation = Modulation::Bpsk;
    let chunk_max = max_packet_payload(&sizing_cfg).max(1);

    let packed = pack_payload(envelope, None);
    let total = packed_chunk_count(packed.len(), &sizing_cfg);
    if total > 4095 {
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
        let mut retries = 0usize;
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
            match listen_once(&cap, &cfg, LISTEN_WINDOW, LISTEN_TAIL_SECONDS) {
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
                    if ok {
                        break;
                    }
                    retries += 1;
                    if retries >= MAX_PACKET_RETRIES {
                        missing.push(seq as u16);
                        break;
                    }
                }
                _ => break,
            }
        }
    }

    let mut targets: Option<Vec<u16>> = if missing.is_empty() {
        None
    } else {
        Some(missing)
    };
    let mut full_replays = 0usize;
    for _round in 1..=MAX_ROUNDS {
        if stop.load(Ordering::SeqCst) {
            return Ok("Передача остановлена.".to_string());
        }
        if let Some(t) = &targets {
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
        match wait_ctrl_on(app, &stop, &cfg, &cap, ACK_WAIT) {
            CtrlWait::Ack(t) if t as usize == total => {
                return Ok("Доставлено: приёмник подтвердил получение.".to_string());
            }
            CtrlWait::Nak(t, miss) if t as usize == total => {
                let miss: Vec<u16> = miss.into_iter().filter(|&s| (s as usize) < total).collect();
                if miss.is_empty() {
                    return Ok("Доставлено: приёмник подтвердил получение.".to_string());
                }
                targets = Some(miss);
            }
            CtrlWait::Ack(_) | CtrlWait::Nak(_, _) | CtrlWait::Rate { .. } => {}
            CtrlWait::Timeout => {
                if targets.is_none() {
                    if full_replays < MAX_FULL_REPLAYS {
                        full_replays += 1;
                        targets = Some((0..total as u16).collect());
                        let _ = app.emit(
                            "modem-status",
                            "Ответа нет — повторяю передачу полностью...".to_string(),
                        );
                    } else {
                        return Ok("Передано, но подтверждение не получено.".to_string());
                    }
                }
            }
            CtrlWait::Stopped => return Ok("Передача остановлена.".to_string()),
        }
    }
    Ok("Передано, подтверждение после повторов не получено.".to_string())
}
