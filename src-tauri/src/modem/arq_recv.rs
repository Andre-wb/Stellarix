use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager};

use audiodsp::ofdm::{
    encode_one_packet, encode_transmission, pack_payload, scan_packets, unpack_payload,
    Modulation, OfdmConfig, RateAdapter,
};

use super::capture::{start_capture, Capture};
use super::filepolicy;
use super::hexutil::to_hex;
use super::player::OutputPlayer;
use super::proto::{self, Frame};
use super::reassembly::{Ingest, Reassembler};
use super::session::tail_at;
use super::storage;

const RECV_TIMEOUT: Duration = Duration::from_secs(240);
const QUIET: Duration = Duration::from_secs(5);
const MAX_NAKS: usize = 8;
const NAK_LIST_CAP: usize = 500;
const POLL_INTERVAL: Duration = Duration::from_millis(150);
const DATA_TAIL_SECONDS: f32 = 6.0;
const ECHO_MUTE: Duration = Duration::from_millis(250);

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
    saved: bool,
    reason: String,
}

pub struct Listener {
    stop: Arc<AtomicBool>,
}

impl Listener {
    pub fn signal_stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}

pub fn start(app: AppHandle, key: Option<[u8; 32]>) -> Result<Listener, String> {
    let cap = start_capture()?;
    let out = OutputPlayer::open()?;
    let stop = Arc::new(AtomicBool::new(false));
    let flag = stop.clone();
    std::thread::spawn(move || {
        if let Err(e) = receive_loop(&app, &flag, cap, out, key) {
            let _ = app.emit("modem-error", e);
        }
    });
    Ok(Listener { stop })
}

fn build_control_wave(bytes: &[u8], cfg: &OfdmConfig) -> Vec<f32> {
    let mut ctrl_cfg = cfg.clone();
    ctrl_cfg.modulation = Modulation::Bpsk;
    let packed = pack_payload(bytes, None);
    let pkt = encode_one_packet(&packed, 0, &ctrl_cfg).unwrap_or_default();
    let pad = (ctrl_cfg.fs / 20) as usize;
    let mut out = vec![0f32; pad];
    out.extend(pkt);
    out.extend(std::iter::repeat_n(0f32, pad));
    out
}

fn receive_loop(
    app: &AppHandle,
    stop: &Arc<AtomicBool>,
    cap: Capture,
    out: OutputPlayer,
    key: Option<[u8; 32]>,
) -> Result<(), String> {
    let cfg = OfdmConfig::default_48k();
    let mut play_cfg = cfg.clone();
    play_cfg.headroom = audiodsp::PLAYBACK_GAIN.clamp(0.05, 1.0);
    play_cfg.modulation = Modulation::Bpsk;

    let mut adapter = RateAdapter::new(Modulation::Bpsk);
    let mut reasm = Reassembler::new();
    let mut deadline = Instant::now() + RECV_TIMEOUT;
    let mut last_progress = Instant::now();
    let mut mute_until = Instant::now();
    let mut naks = 0usize;

    loop {
        std::thread::sleep(POLL_INTERVAL);
        let _ = app.emit("modem-level", cap.level());
        if stop.load(Ordering::SeqCst) {
            let msg = match reasm.total() {
                Some(t) => format!(
                    "Приём остановлен: разобрано {} из {t} пакетов — этого не хватило, начните приём заново.",
                    reasm.have()
                ),
                None => "Приём остановлен: ни одного пакета распознать не удалось.".to_string(),
            };
            let _ = app.emit("modem-stopped", msg);
            return Ok(());
        }
        if Instant::now() >= deadline {
            let _ = app.emit(
                "modem-error",
                "Не удалось принять данные полностью. Сблизьте устройства, увеличьте громкость и повторите.".to_string(),
            );
            return Ok(());
        }

        if Instant::now() >= mute_until {
            let max_raw = (cap.sample_rate as f32 * DATA_TAIL_SECONDS) as usize;
            let (snap, raw_start) = tail_at(&cap, cfg.fs, max_raw);
            let ratio = cap.sample_rate as f64 / cfg.fs as f64;
            let mut news = false;
            for pkt in scan_packets(&snap, &cfg) {
                let abs = raw_start + (pkt.start_sample as f64 * ratio).round() as usize;
                let seq = pkt.header.seq as usize;
                let hdr_total = pkt.header.total as usize;
                if !matches!(reasm.ingest(abs, seq, hdr_total), Ingest::Accepted) {
                    continue;
                }
                let ok = pkt.payload.is_some();

                let previous = adapter.current();
                let recommended = if ok {
                    adapter.observe_snr(pkt.snr_db)
                } else {
                    adapter.observe_failure()
                };
                if ok {
                    if let Some(payload) = pkt.payload {
                        reasm.store(seq, payload);
                        news = true;
                    }
                }
                if !ok || recommended != previous {
                    let bytes = proto::encode_rate(seq as u16, ok, recommended.id(), pkt.snr_db);
                    let wave = build_control_wave(&bytes, &play_cfg);
                    out.play(&wave, cfg.fs, stop)?;
                    mute_until = Instant::now() + ECHO_MUTE;
                }
            }
            if news {
                last_progress = Instant::now();
                deadline = Instant::now() + RECV_TIMEOUT;
                if let Some(t) = reasm.total() {
                    let _ = app.emit(
                        "modem-packets",
                        Packets {
                            have: reasm.have(),
                            total: t,
                        },
                    );
                }
            }
        }

        if reasm.is_complete() {
            let packed = reasm.assemble();
            let decoded = key
                .as_ref()
                .and_then(|k| unpack_payload(&packed, Some(k)))
                .or_else(|| unpack_payload(&packed, None));
            let Some(envelope) = decoded else {
                let _ = app.emit(
                    "modem-error",
                    "Данные приняты, но распаковать их не удалось.".to_string(),
                );
                return Ok(());
            };
            let _ = app.emit("modem-status", "Отправляю подтверждение приёма...".to_string());
            let t = reasm.total().unwrap_or(0);
            let wave = encode_transmission(&proto::encode_ack(t as u16), &play_cfg);
            let _ = out.play(&wave, cfg.fs, stop);
            std::thread::sleep(Duration::from_millis(200));
            let _ = out.play(&wave, cfg.fs, stop);
            handle_envelope(app, envelope)?;
            return Ok(());
        }

        if Instant::now() >= mute_until && reasm.has_parts() && last_progress.elapsed() >= QUIET {
            if let (true, Some(t)) = (naks < MAX_NAKS, reasm.total()) {
                let missing = reasm.missing_list(NAK_LIST_CAP);
                naks += 1;
                let _ = app.emit(
                    "modem-status",
                    format!("Запрашиваю повтор {} пакетов...", missing.len()),
                );
                let wave = encode_transmission(&proto::encode_nak(t as u16, &missing), &play_cfg);
                out.play(&wave, cfg.fs, stop)?;
                mute_until = Instant::now() + ECHO_MUTE;
                last_progress = Instant::now();
                let _ = app.emit("modem-status", "Жду повторную передачу...".to_string());
            } else {
                let _ = app.emit(
                    "modem-error",
                    "Не удалось принять данные полностью. Сблизьте устройства, увеличьте громкость и повторите.".to_string(),
                );
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
            let hash_ok = storage::hash_matches(&content, &sha256);
            let safe = proto::sanitize_filename(&name);
            let mut path = String::new();
            let mut saved = false;
            let mut reason = String::new();
            if !hash_ok {
                reason = "SHA-256 не совпала — файл повреждён при передаче".to_string();
            } else if let Err(e) = filepolicy::check(&safe, &content) {
                reason = format!("формат отклонён политикой безопасности: {e}");
            } else {
                path = save_file(app, &safe, &content)?;
                saved = true;
            }
            let _ = app.emit(
                "modem-file",
                FileEvent {
                    name: safe,
                    size: content.len(),
                    path,
                    hash_ok,
                    saved,
                    reason,
                },
            );
        }
        Some(Frame::Nak { .. }) | Some(Frame::Ack { .. }) | Some(Frame::Rate { .. }) => {
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
    let path = storage::store_unique(&dir, safe_name, content)
        .map_err(|e| format!("Не удалось сохранить файл: {e}"))?;
    Ok(path.display().to_string())
}
