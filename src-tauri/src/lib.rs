#![cfg_attr(target_os = "android", allow(dead_code))]

mod commands;
mod modem;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use tauri::{async_runtime, AppHandle, Emitter, Manager};
use tokio::sync::Mutex;
use tokio::net::TcpStream;
use tracing::{info, error, debug};
use tracing_subscriber::{fmt, EnvFilter};

const APP_PORT: u16 = 8000;

fn log_file_path() -> PathBuf {
    std::env::temp_dir().join("stellarix-startup.log")
}

fn setup_logging() -> Option<tracing_appender::non_blocking::WorkerGuard> {
    use tracing_subscriber::prelude::*;

    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    let stdout_layer = fmt::layer()
        .with_ansi(true)
        .with_target(true)
        .with_thread_ids(true)
        .with_thread_names(true)
        .with_file(true)
        .with_line_number(true)
        .with_level(true)
        .with_timer(fmt::time::ChronoLocal::rfc_3339());

    let log_path = log_file_path();
    let file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path);

    match file {
        Ok(file) => {
            let (writer, guard) = tracing_appender::non_blocking(file);
            let file_layer = fmt::layer()
                .with_ansi(false)
                .with_target(true)
                .with_thread_ids(true)
                .with_thread_names(true)
                .with_file(true)
                .with_line_number(true)
                .with_level(true)
                .with_timer(fmt::time::ChronoLocal::rfc_3339())
                .with_writer(writer);
            tracing_subscriber::registry()
                .with(env_filter)
                .with(stdout_layer)
                .with(file_layer)
                .init();
            info!("🚀 Логирование инициализировано, лог-файл: {}", log_path.display());
            Some(guard)
        }
        Err(e) => {
            tracing_subscriber::registry()
                .with(env_filter)
                .with(stdout_layer)
                .init();
            info!("🚀 Логирование инициализировано (файл {} недоступен: {e})", log_path.display());
            None
        }
    }
}

fn create_private_dir(path: &std::path::Path) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        std::fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(path)
            .map_err(|e| format!("Не удалось создать каталог {}: {e}", path.display()))
    }
    #[cfg(not(unix))]
    {
        std::fs::create_dir_all(path)
            .map_err(|e| format!("Не удалось создать каталог {}: {e}", path.display()))
    }
}

async fn wait_for_port(addr: SocketAddr, timeout: Duration) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed() < timeout {
        match TcpStream::connect(addr).await {
            Ok(_) => return true,
            Err(_) => {
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
    false
}

fn stage(app: &AppHandle, since: std::time::Instant, msg: &str) {
    info!("[этап +{} мс] {}", since.elapsed().as_millis(), msg);
    let _ = app.emit("server-progress", msg.to_string());
}

async fn bring_up(app: AppHandle) -> Result<String, String> {
    let t0 = std::time::Instant::now();
    info!(
        "Запуск приложения Tauri... ОС: {} / {}",
        std::env::consts::OS,
        std::env::consts::ARCH
    );

    let data_dir = app.path().app_data_dir()
        .map_err(|e| format!("Нет каталога данных приложения: {e}"))?;
    debug!("data_dir: {}", data_dir.display());
    create_private_dir(&data_dir)?;

    let static_dir = {
        let res = app.path().resource_dir().ok();
        let bundled = res.as_ref().map(|d| d.join("static")).filter(|p| p.exists())
            .or_else(|| res.as_ref().map(|d| d.join("_up_").join("static")).filter(|p| p.exists()));
        bundled.unwrap_or_else(|| PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../static")))
    };
    debug!("static_dir: {}", static_dir.display());

    // Настраиваем переменные окружения
    std::env::set_var("APP_ENVIRONMENT", "development");
    std::env::set_var("LOG_LEVEL", "info");

    stage(&app, t0, "Инициализация SQLite...");
    let db_path = data_dir.join("stellarix.db");
    let pool = stellarix::db_sqlite::init_pool(db_path).await.map_err(|e| {
        error!("Ошибка базы данных: {}", e);
        format!("База данных: {e}")
    })?;
    info!("✅ SQLite база данных создана");

    stage(&app, t0, "Инициализация конфигурации приложения...");
    // Устанавливаем DATABASE_URL для SQLite (не используется, но требуется для Config)
    std::env::set_var("DATABASE_URL", &format!("sqlite:{}", data_dir.join("stellarix.db").display()));
    std::env::set_var("USERNAME_SECRET", "dev_secret_32_bytes_here_xxxxxx");
    std::env::set_var("SESSION_SECRET", "dev_session_secret_32_bytes_here");

    stellarix::config::Config::init().map_err(|e| {
        error!("Ошибка конфигурации: {}", e);
        format!("Конфигурация: {e}")
    })?;

    stage(&app, t0, "Занимаю порт приложения...");
    let addr = SocketAddr::from(([127, 0, 0, 1], APP_PORT));
    let listener = tokio::net::TcpListener::bind(addr).await
        .map_err(|e| {
            error!("Не удалось занять порт {}: {}", APP_PORT, e);
            format!("Не удалось занять порт {APP_PORT}: {e}")
        })?;
    info!("Слушатель создан на порту {}", APP_PORT);

    let url = format!("http://127.0.0.1:{APP_PORT}/");

    // Запускаем сервер
    let server_handle = tokio::spawn(async move {
        info!("Запуск сервера в фоновом потоке...");
        if let Err(e) = stellarix::serve_on(listener, pool, static_dir, false).await {
            error!("Ошибка сервера: {}", e);
        }
        info!("Сервер остановлен");
    });

    // Ждём, пока сервер начнёт слушать порт
    stage(&app, t0, "Ожидание готовности веб-сервера...");
    if wait_for_port(addr, Duration::from_secs(5)).await {
        info!("✅ Сервер готов и принимает соединения");
    } else {
        error!("❌ Сервер не запустился в течение 5 секунд");
        server_handle.abort();
        return Err("Сервер не запустился".to_string());
    }

    // Отправляем событие фронтенду
    stage(&app, t0, "Сервер готов, отправляю server-ready...");
    app.emit("server-ready", url.clone()).map_err(|e| {
        error!("Ошибка отправки события server-ready: {}", e);
        format!("emit: {e}")
    })?;
    info!("📡 Событие server-ready отправлено");

    info!("✅ Сервер запущен в фоновом режиме");
    Ok(url)
}

// ============ Desktop Entry Point ============
#[cfg(not(target_os = "android"))]
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg(not(target_os = "android"))]
pub fn run_desktop() {
    let _log_guard = setup_logging();
    info!("=== 🚀 Запуск Tauri приложения (Desktop) ===");
    info!("Лог старта пишется в файл: {}", log_file_path().display());

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(commands::ListenerState::default())
        .manage(commands::PlaybackState::default())
        .invoke_handler(tauri::generate_handler![
            commands::play_payload,
            commands::send_file,
            commands::stop_playing,
            commands::start_listening,
            commands::stop_listening,
        ])
        .setup(move |app| {
            info!("Настройка приложения...");
            let handle = app.handle().clone();
            async_runtime::spawn(async move {
                if let Err(e) = bring_up(handle.clone()).await {
                    error!("❌ Ошибка запуска: {}", e);
                    let _ = handle.emit("server-error", &e);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("не удалось инициализировать Tauri")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                info!("Получен запрос на выход");
                info!("✅ Приложение завершено");
            }
        });
}

#[cfg(not(target_os = "android"))]
fn main() {
    run_desktop();
}