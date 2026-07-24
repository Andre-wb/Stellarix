use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, Manager};

use audiodsp::ofdm::{decode_stream, encode_transmission, unpack_payload, OfdmConfig};

use super::capture::start_capture;
use super::hexutil::to_hex;
use super::player::play_wave;
use super::proto::{self, Frame};
use super::session::snapshot_at;

const RECV_TIMEOUT: Duration = Duration::from_secs(240);
const QUIET: Duration = Duration::from_secs(5);
const MAX_NAKS: usize = 8;
const NAK_LIST_CAP: usize = 500;

#[derive(Clone, serde::Serialize)]
struct Packets {
    have: usize,
    total: usize,
}

#[derive(Clone, serde::Serialize)]
struct FileEvent {
    name: String,
    size: usize,
    path: String,
    hash_ok: bool,
}

enum Outcome {
    Complete,
    SendNak,
    Stopped,
    Deadline,
}

pub fn run_receive(app: AppHandle, stop: Arc<AtomicBool>) {
    if let Err(e) = receive_loop(&app, &stop) {
        let _ = app.emit("modem-error", e);
    }
}

fn receive_loop(app: &AppHandle, stop: &Arc<AtomicBool>) -> Result<(), String> {
    let cfg = OfdmConfig::default_48k();
    let mut play_cfg = cfg.clone();
    play_cfg.headroom = audiodsp::PLAYBACK_GAIN.clamp(0.05, 1.0);
    let mut deadline = Instant::now() + RECV_TIMEOUT;
    let mut parts: HashMap<usize, Vec<u8>> = HashMap::new();
    let mut total: Option<usize> = None;
    let mut naks = 0usize;
    loop {
        let cap = start_capture()?;
        let mut scan_from = 0usize;
        let mut last_decode_len = 0usize;
        let mut last_progress = Instant::now();
        let outcome = loop {
            std::thread::sleep(Duration::from_millis(250));
            let _ = app.emit("modem-level", cap.level());
            if stop.load(Ordering::SeqCst) {
                break Outcome::Stopped;
            }
            if Instant::now() >= deadline {
                break Outcome::Deadline;
            }
            let len = cap.len();
            if len >= last_decode_len + cfg.fs as usize * 2 {
                last_decode_len = len;
                let snap = snapshot_at(&cap, cfg.fs);
                let rep = decode_stream(&snap, &cfg, scan_from);
                scan_from = rep.consumed;
                if total.is_none() {
                    total = rep.total;
                }
                if let Some(t) = total {
                    let mut news = false;
                    if rep.total.is_none() || rep.total == Some(t) {
                        for (s, p) in rep.parts {
                            if s < t && !parts.contains_key(&s) {
                                parts.insert(s, p);
                                news = true;
                            }
                        }
                    }
                    if news {
                        last_progress = Instant::now();
                        deadline = Instant::now() + RECV_TIMEOUT;
                        let _ = app.emit(
                            "modem-packets",
                            Packets {
                                have: parts.len(),
                                total: t,
                            },
                        );
                    }
                    if parts.len() >= t {
                        break Outcome::Complete;
                    }
                }
            }
            if !parts.is_empty() && total.is_some() && last_progress.elapsed() >= QUIET {
                if naks < MAX_NAKS {
                    break Outcome::SendNak;
                }
                break Outcome::Deadline;
            }
        };
        drop(cap);
        match outcome {
            Outcome::Stopped => {
                let _ = app.emit("modem-stopped", "Приём остановлен.".to_string());
                return Ok(());
            }
            Outcome::Deadline => {
                let _ = app.emit(
                    "modem-error",
                    "Не удалось принять данные полностью. Сблизьте устройства, увеличьте громкость и повторите.".to_string(),
                );
                return Ok(());
            }
            Outcome::SendNak => {
                let t = total.unwrap();
                let missing: Vec<u16> = (0..t)
                    .filter(|s| !parts.contains_key(s))
                    .map(|s| s as u16)
                    .take(NAK_LIST_CAP)
                    .collect();
                naks += 1;
                let _ = app.emit(
                    "modem-status",
                    format!("Запрашиваю повтор {} пакетов...", missing.len()),
                );
                let wave =
                    encode_transmission(&proto::encode_nak(t as u16, &missing), &play_cfg);
                let _ = play_wave(&wave, play_cfg.fs);
                let _ = app.emit("modem-status", "Жду повторную передачу...".to_string());
            }
            Outcome::Complete => {
                let t = total.unwrap();
                let mut packed = Vec::new();
                for s in 0..t {
                    packed.extend_from_slice(&parts[&s]);
                }
                let Some(envelope) = unpack_payload(&packed, None) else {
                    let _ = app.emit(
                        "modem-error",
                        "Данные приняты, но распаковать их не удалось.".to_string(),
                    );
                    return Ok(());
                };
                handle_envelope(app, envelope)?;
                let _ = app.emit("modem-status", "Отправляю подтверждение приёма...".to_string());
                let wave = encode_transmission(&proto::encode_ack(t as u16), &play_cfg);
                let _ = play_wave(&wave, play_cfg.fs);
                std::thread::sleep(Duration::from_millis(200));
                let _ = play_wave(&wave, play_cfg.fs);
                return Ok(());
            }
        }
    }
}

fn handle_envelope(app: &AppHandle, envelope: Vec<u8>) -> Result<(), String> {
    match proto::parse(&envelope) {
        Some(Frame::Msg(body)) => {
            let _ = app.emit("modem-decoded", to_hex(&body));
        }
        Some(Frame::File {
            name,
            sha256,
            content,
        }) => {
            let mut hasher = Sha256::new();
            hasher.update(&content);
            let hash_ok = hasher.finalize().as_slice() == sha256;
            let safe = proto::sanitize_filename(&name);
            let path = save_file(app, &safe, &content)?;
            let _ = app.emit(
                "modem-file",
                FileEvent {
                    name: safe,
                    size: content.len(),
                    path,
                    hash_ok,
                },
            );
        }
        Some(Frame::Nak { .. }) | Some(Frame::Ack { .. }) => {
            let _ = app.emit(
                "modem-error",
                "Принят служебный сигнал вместо данных. Повторите передачу.".to_string(),
            );
        }
        None => {
            let _ = app.emit("modem-decoded", to_hex(&envelope));
        }
    }
    Ok(())
}

fn save_file(app: &AppHandle, safe_name: &str, content: &[u8]) -> Result<String, String> {
    let dir = app
        .path()
        .download_dir()
        .or_else(|_| app.path().app_data_dir())
        .map_err(|e| format!("Нет каталога для сохранения файла: {e}"))?;
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("Не удалось создать каталог {}: {e}", dir.display()))?;
    let (stem, ext) = split_name(safe_name);
    let mut candidate = dir.join(safe_name);
    let mut i = 1;
    while candidate.exists() {
        let alt = if ext.is_empty() {
            format!("{stem} ({i})")
        } else {
            format!("{stem} ({i}).{ext}")
        };
        candidate = dir.join(alt);
        i += 1;
    }
    std::fs::write(&candidate, content)
        .map_err(|e| format!("Не удалось сохранить файл: {e}"))?;
    Ok(candidate.display().to_string())
}

fn split_name(name: &str) -> (String, String) {
    match name.rsplit_once('.') {
        Some((s, e)) if !s.is_empty() => (s.to_string(), e.to_string()),
        _ => (name.to_string(), String::new()),
    }
}
