use std::sync::Mutex;

use tauri::{AppHandle, State};

use crate::modem;

pub struct ListenerState(pub Mutex<Option<modem::Listener>>);

impl Default for ListenerState {
    fn default() -> Self {
        ListenerState(Mutex::new(None))
    }
}

#[tauri::command]
pub async fn play_payload(hex: String) -> Result<(), String> {
    let payload = hex_to_bytes(&hex)?;
    tauri::async_runtime::spawn_blocking(move || modem::play(&payload, audiodsp::PLAYBACK_GAIN))
        .await
        .map_err(|e| format!("сбой потока воспроизведения: {e}"))?
}

#[tauri::command]
pub fn start_listening(app: AppHandle, state: State<ListenerState>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|_| "состояние занято".to_string())?;
    if let Some(old) = guard.take() {
        old.signal_stop();
    }
    let listener = modem::start(app)?;
    *guard = Some(listener);
    Ok(())
}

#[tauri::command]
pub fn stop_listening(state: State<ListenerState>) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(listener) = guard.take() {
            listener.signal_stop();
        }
    }
}

fn hex_to_bytes(hex: &str) -> Result<Vec<u8>, String> {
    if hex.len() % 2 != 0 {
        return Err("нечётная длина hex".to_string());
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).map_err(|_| "некорректный hex".to_string()))
        .collect()
}
