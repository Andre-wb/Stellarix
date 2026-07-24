use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, State};

use crate::modem;

pub struct ListenerState(pub Mutex<Option<modem::Listener>>);

impl Default for ListenerState {
    fn default() -> Self {
        ListenerState(Mutex::new(None))
    }
}

#[derive(Default)]
pub struct PlaybackState(pub Mutex<Option<Arc<AtomicBool>>>);

#[tauri::command]
pub async fn play_payload(
    app: AppHandle,
    state: State<'_, PlaybackState>,
    hex: String,
) -> Result<bool, String> {
    let payload = hex_to_bytes(&hex)?;
    let stop = Arc::new(AtomicBool::new(false));
    {
        let mut guard = state.0.lock().map_err(|_| "состояние занято".to_string())?;
        if let Some(prev) = guard.replace(stop.clone()) {
            prev.store(true, Ordering::SeqCst);
        }
    }
    let handle = app.clone();
    let flag = stop.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        modem::play(&payload, audiodsp::PLAYBACK_GAIN, &flag, |seq, total| {
            let _ = handle.emit(
                "modem-status",
                format!("Передаю пакет {}/{}...", seq + 1, total),
            );
        })
    })
    .await
    .map_err(|e| format!("сбой потока воспроизведения: {e}"))?;
    if let Ok(mut guard) = state.0.lock() {
        if guard.as_ref().is_some_and(|cur| Arc::ptr_eq(cur, &stop)) {
            guard.take();
        }
    }
    result
}

#[tauri::command]
pub fn stop_playing(state: State<PlaybackState>) {
    if let Ok(guard) = state.0.lock() {
        if let Some(stop) = guard.as_ref() {
            stop.store(true, Ordering::SeqCst);
        }
    }
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
