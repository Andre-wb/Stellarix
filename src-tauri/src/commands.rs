use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, State};

use crate::modem;

pub struct ListenerState(pub Mutex<Option<modem::Listener>>);

impl Default for ListenerState {
    fn default() -> Self {
        ListenerState(Mutex::new(None))
    }
}

#[derive(Default)]
pub struct PlaybackState(pub Mutex<Option<Arc<AtomicBool>>>);

const MAX_FILE_BYTES: usize = 64 * 1024;

async fn run_playback<F>(state: State<'_, PlaybackState>, send: F) -> Result<bool, String>
where
    F: FnOnce(Arc<AtomicBool>) -> Result<String, String> + Send + 'static,
{
    let stop = Arc::new(AtomicBool::new(false));
    {
        let mut guard = state.0.lock().map_err(|_| "состояние занято".to_string())?;
        if let Some(prev) = guard.replace(stop.clone()) {
            prev.store(true, Ordering::SeqCst);
        }
    }
    let flag = stop.clone();
    let joined = tauri::async_runtime::spawn_blocking(move || {
        send(flag.clone()).map(|_| !flag.load(Ordering::SeqCst))
    })
    .await;
    if let Ok(mut guard) = state.0.lock() {
        if guard.as_ref().is_some_and(|cur| Arc::ptr_eq(cur, &stop)) {
            guard.take();
        }
    }
    joined.map_err(|e| format!("сбой потока воспроизведения: {e}"))?
}

#[tauri::command]
pub async fn play_payload(
    app: AppHandle,
    state: State<'_, PlaybackState>,
    hex: String,
) -> Result<bool, String> {
    let payload = hex_to_bytes(&hex)?;
    run_playback(state, move |stop| modem::run_send_msg(&app, stop, &payload)).await
}

#[tauri::command]
pub async fn send_file(
    app: AppHandle,
    state: State<'_, PlaybackState>,
    name: String,
    hex: String,
) -> Result<bool, String> {
    let content = hex_to_bytes(&hex)?;
    if content.is_empty() {
        return Err("файл пуст".to_string());
    }
    if content.len() > MAX_FILE_BYTES {
        return Err(format!(
            "файл слишком большой для передачи звуком: максимум {} КиБ",
            MAX_FILE_BYTES / 1024
        ));
    }
    modem::check_file_policy(&name, &content)?;
    run_playback(state, move |stop| {
        modem::run_send_file(&app, stop, &name, &content)
    })
    .await
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_hex_is_empty_bytes() {
        assert_eq!(hex_to_bytes("").unwrap(), Vec::<u8>::new());
    }

    #[test]
    fn decodes_lower_and_upper_case() {
        assert_eq!(hex_to_bytes("00ffA7").unwrap(), vec![0x00, 0xff, 0xa7]);
        assert_eq!(hex_to_bytes("deadBEEF").unwrap(), vec![0xde, 0xad, 0xbe, 0xef]);
    }

    #[test]
    fn rejects_odd_length() {
        assert_eq!(hex_to_bytes("abc").unwrap_err(), "нечётная длина hex");
    }

    #[test]
    fn rejects_non_hex_digits() {
        assert_eq!(hex_to_bytes("zz").unwrap_err(), "некорректный hex");
        assert_eq!(hex_to_bytes("0g").unwrap_err(), "некорректный hex");
    }
}
