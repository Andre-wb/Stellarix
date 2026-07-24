use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tauri::{AppHandle, Emitter};

use audiodsp::ofdm::{
    encode_packed_transmission, pack_payload, packed_chunk_count, Modulation, OfdmConfig,
};

use super::player::play_wave;
use super::session::{wait_ctrl, CtrlWait};

const MAX_ROUNDS: usize = 6;
const MAX_FULL_REPLAYS: usize = 1;
const ACK_WAIT: Duration = Duration::from_secs(12);

pub fn run_send(
    app: &AppHandle,
    stop: Arc<AtomicBool>,
    envelope: &[u8],
    modulation: Modulation,
) -> Result<String, String> {
    let mut cfg = OfdmConfig::default_48k();
    cfg.headroom = audiodsp::PLAYBACK_GAIN.clamp(0.05, 1.0);
    cfg.modulation = modulation;
    let packed = pack_payload(envelope, None);
    let total = packed_chunk_count(packed.len(), &cfg);
    if total > 4095 {
        return Err("Данные слишком велики для передачи звуком.".to_string());
    }
    let mut targets: Option<Vec<u16>> = None;
    let mut full_replays = 0usize;
    for round in 1..=MAX_ROUNDS {
        if stop.load(Ordering::SeqCst) {
            return Ok("Передача остановлена.".to_string());
        }
        let n_now = targets.as_ref().map(|t| t.len()).unwrap_or(total);
        let _ = app.emit(
            "modem-status",
            format!("Передаю {n_now} из {total} пакетов (попытка {round})..."),
        );
        let wave = encode_packed_transmission(&packed, &cfg, targets.as_deref());
        play_wave(&wave, cfg.fs)?;
        let _ = app.emit("modem-status", "Жду подтверждение приёма...".to_string());
        match wait_ctrl(app, &stop, &cfg, ACK_WAIT) {
            CtrlWait::Ack(t) if t as usize == total => {
                return Ok("Доставлено: приёмник подтвердил получение.".to_string());
            }
            CtrlWait::Nak(t, missing) if t as usize == total => {
                let miss: Vec<u16> = missing
                    .into_iter()
                    .filter(|&s| (s as usize) < total)
                    .collect();
                if miss.is_empty() {
                    return Ok("Доставлено: приёмник подтвердил получение.".to_string());
                }
                targets = Some(miss);
            }
            CtrlWait::Ack(_) | CtrlWait::Nak(_, _) => {}
            CtrlWait::Timeout => {
                if full_replays < MAX_FULL_REPLAYS {
                    full_replays += 1;
                    targets = None;
                    let _ = app.emit(
                        "modem-status",
                        "Ответа нет — повторяю передачу полностью...".to_string(),
                    );
                } else {
                    return Ok("Передано, но подтверждение не получено.".to_string());
                }
            }
            CtrlWait::Stopped => return Ok("Передача остановлена.".to_string()),
            CtrlWait::Failed(e) => return Err(e),
        }
    }
    Ok("Передано, подтверждение после повторов не получено.".to_string())
}
