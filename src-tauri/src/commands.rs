use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use sha2::{Digest, Sha256};
use tauri::{AppHandle, State};

use crate::modem;
use crate::modem::hexutil::from_hex;
use crate::modem::proto;

const MAX_FILE_BYTES: usize = 4 * 1024 * 1024;

pub struct ModemState(pub Mutex<Option<Arc<AtomicBool>>>);

impl Default for ModemState {
    fn default() -> Self {
        ModemState(Mutex::new(None))
    }
}

fn begin(state: &State<'_, ModemState>) -> Result<Arc<AtomicBool>, String> {
    let mut guard = state.0.lock().map_err(|_| "состояние занято".to_string())?;
    if let Some(old) = guard.take() {
        old.store(true, Ordering::SeqCst);
    }
    let flag = Arc::new(AtomicBool::new(false));
    *guard = Some(flag.clone());
    Ok(flag)
}

fn parse_modulation(name: Option<&str>) -> Result<audiodsp::ofdm::Modulation, String> {
    match name {
        None => Ok(audiodsp::ofdm::Modulation::Qpsk),
        Some(s) => s
            .parse()
            .map_err(|_| format!("неизвестная модуляция: {s}")),
    }
}

#[tauri::command]
pub async fn send_payload_arq(
    app: AppHandle,
    state: State<'_, ModemState>,
    hex: String,
    modulation: Option<String>,
) -> Result<String, String> {
    let body = from_hex(&hex)?;
    let modulation = parse_modulation(modulation.as_deref())?;
    let stop = begin(&state)?;
    let envelope = proto::encode_msg(&body);
    tauri::async_runtime::spawn_blocking(move || modem::run_send(&app, stop, &envelope, modulation))
        .await
        .map_err(|e| format!("сбой потока передачи: {e}"))?
}

#[tauri::command]
pub async fn send_file_arq(
    app: AppHandle,
    state: State<'_, ModemState>,
    name: String,
    hex: String,
    modulation: Option<String>,
) -> Result<String, String> {
    let content = from_hex(&hex)?;
    if content.is_empty() {
        return Err("Файл пуст.".to_string());
    }
    if content.len() > MAX_FILE_BYTES {
        return Err("Файл больше 4 МБ — для звукового канала это слишком много.".to_string());
    }
    let modulation = parse_modulation(modulation.as_deref())?;
    let stop = begin(&state)?;
    let mut hasher = Sha256::new();
    hasher.update(&content);
    let digest: [u8; 32] = hasher.finalize().into();
    let envelope = proto::encode_file(&name, &digest, &content);
    tauri::async_runtime::spawn_blocking(move || modem::run_send(&app, stop, &envelope, modulation))
        .await
        .map_err(|e| format!("сбой потока передачи: {e}"))?
}

#[tauri::command]
pub fn start_listening(app: AppHandle, state: State<'_, ModemState>) -> Result<(), String> {
    let stop = begin(&state)?;
    std::thread::spawn(move || modem::run_receive(app, stop));
    Ok(())
}

#[tauri::command]
pub fn stop_listening(state: State<'_, ModemState>) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(flag) = guard.take() {
            flag.store(true, Ordering::SeqCst);
        }
    }
}
