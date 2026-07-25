#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod modem;
mod pgcleanup;
mod pgpaths;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use postgresql_embedded::{PostgreSQL, Settings};
use tauri::{async_runtime, AppHandle, Emitter, Manager};
use tokio::sync::Mutex;
use tokio::net::TcpStream;
use tracing::{info, error, debug};
use tracing_subscriber::{fmt, EnvFilter};

const APP_PORT: u16 = 8000;
const PG_PORT: u16 = 15432;
const DB_NAME: &str = "stellarix";
const PG_USER: &str = "postgres";

struct PgGuard(Arc<Mutex<Option<PostgreSQL>>>);

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

fn random_hex(n: usize) -> String {
    use rand::RngCore;
    let mut buf = vec![0u8; n];
    rand::rngs::OsRng.fill_bytes(&mut buf);
    buf.iter().map(|b| format!("{:02x}", b)).collect()
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

fn write_private(path: &std::path::Path, value: &str) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::io::Write;
        use std::os::unix::fs::OpenOptionsExt;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(path)
            .map_err(|e| format!("Не удалось создать {}: {e}", path.display()))?;
        file.write_all(value.as_bytes())
            .map_err(|e| format!("Не удалось записать {}: {e}", path.display()))
    }
    #[cfg(not(unix))]
    {
        std::fs::write(path, value)
            .map_err(|e| format!("Не удалось записать {}: {e}", path.display()))
    }
}

fn load_or_create_secret(dir: &PathBuf, name: &str) -> Result<String, String> {
    let path = dir.join(name);
    if let Ok(existing) = std::fs::read_to_string(&path) {
        let trimmed = existing.trim().to_string();
        if !trimmed.is_empty() {
            return Ok(trimmed);
        }
    }
    let value = random_hex(32);
    write_private(&path, &value)?;
    Ok(value)
}

async fn init_db_with_c_locale(
    pg: &PostgreSQL,
    data_dir: &std::path::Path,
    password_file: &std::path::Path,
    password: &str,
) -> Result<(), String> {
    let initdb = pg
        .settings()
        .binary_dir()
        .join(if cfg!(windows) { "initdb.exe" } else { "initdb" });
    if !initdb.exists() {
        return Err(format!("initdb не найден: {}", initdb.display()));
    }

    write_private(password_file, password)?;
    let _ = std::fs::remove_dir_all(data_dir);
    create_private_dir(data_dir)?;

    info!("Запуск initdb вручную: {} (--locale=C --encoding=UTF8)", initdb.display());
    let output = tokio::process::Command::new(&initdb)
        .arg("--pgdata").arg(data_dir)
        .arg("--username").arg(PG_USER)
        .arg("--auth").arg("password")
        .arg("--pwfile").arg(password_file)
        .arg("--encoding").arg("UTF8")
        .arg("--locale").arg("C")
        .output()
        .await
        .map_err(|e| format!("Не удалось запустить initdb: {e}"))?;

    info!(
        "initdb завершился, код: {:?}, stderr: {}",
        output.status.code(),
        String::from_utf8_lossy(&output.stderr).trim()
    );

    if !output.status.success() {
        return Err(format!(
            "initdb завершился с ошибкой: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(())
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

async fn bring_up(app: AppHandle, pg_state: Arc<Mutex<Option<PostgreSQL>>>) -> Result<String, String> {
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

    info!("Загрузка секретов...");
    std::env::set_var("USERNAME_SECRET", load_or_create_secret(&data_dir, "username_secret")?);
    std::env::set_var("SESSION_SECRET", load_or_create_secret(&data_dir, "session_secret")?);
    std::env::set_var("APP_ENVIRONMENT", "development");
    std::env::set_var("LOG_LEVEL", "info");

    let pg_base = pgpaths::pg_base_dir(&data_dir, &app.config().identifier);
    if pg_base != data_dir {
        create_private_dir(&pg_base)?;
    }
    let pg_data = pg_base.join("pgdata");
    let pg_install = pg_base.join("pg-install");
    create_private_dir(&pg_data)?;
    debug!("Каталог PostgreSQL: {}", pg_data.display());

    stage(&app, t0, "Проверка порта PostgreSQL и старых процессов...");
    pgcleanup::free_stale_instance(&pg_data, PG_PORT).await?;

    let pg_password = load_or_create_secret(&data_dir, "pg_password")?;
    debug!("Пароль PostgreSQL загружен");

    std::env::set_var("LC_ALL", "C");
    std::env::set_var("LANG", "C");
    std::env::set_var("LC_CTYPE", "C");
    std::env::set_var("LC_COLLATE", "C");
    std::env::set_var("LC_MESSAGES", "C");

    let mut settings = Settings::default();
    settings.data_dir = pg_data.clone();
    settings.installation_dir = pg_install;
    settings.host = "127.0.0.1".to_string();
    settings.port = PG_PORT;
    settings.username = PG_USER.to_string();
    settings.password = pg_password.clone();
    settings.password_file = pg_base.join(".pgpass");
    settings.temporary = false;
    settings.timeout = Some(std::time::Duration::from_secs(30));

    stage(&app, t0, "Подготовка PostgreSQL (распаковка бинарников)...");
    let mut pg = PostgreSQL::new(settings.clone());
    if let Err(e) = pg.setup().await {
        error!("Ошибка настройки PostgreSQL: {}, инициализация вручную с локалью C", e);
        stage(&app, t0, "Инициализация базы вручную (initdb, locale=C)...");
        init_db_with_c_locale(&pg, &pg_data, &settings.password_file, &pg_password).await?;
        stage(&app, t0, "Повторная подготовка PostgreSQL после initdb...");
        pg.setup().await.map_err(|e| {
            error!("Ошибка настройки PostgreSQL: {}", e);
            format!("Не удалось подготовить PostgreSQL: {e}")
        })?;
    }

    stage(&app, t0, "Запуск сервера PostgreSQL...");
    pg.start().await.map_err(|e| {
        let log_tail = pgcleanup::start_log_tail(&pg_data, 1500);
        error!("Ошибка запуска PostgreSQL: {} | лог: {:?}", e, log_tail);
        match log_tail {
            Some(tail) => format!("Не удалось запустить PostgreSQL: {e}\n\nЖурнал PostgreSQL:\n{tail}"),
            None => format!("Не удалось запустить PostgreSQL: {e}"),
        }
    })?;
    info!("✅ PostgreSQL успешно запущен");

    {
        let mut guard = pg_state.lock().await;
        *guard = Some(pg);
    }

    let database_url = format!("postgres://{PG_USER}:{pg_password}@127.0.0.1:{PG_PORT}/{DB_NAME}");
    std::env::set_var("DATABASE_URL", &database_url);
    debug!("DATABASE_URL установлена");

    stage(&app, t0, "Инициализация конфигурации приложения...");
    stellarix::config::Config::init().map_err(|e| {
        error!("Ошибка конфигурации: {}", e);
        format!("Конфигурация: {e}")
    })?;

    stage(&app, t0, "Создание пула БД и выполнение миграций...");
    let pool = stellarix::db::init_pool().await.map_err(|e| {
        error!("Ошибка базы данных: {}", e);
        format!("База данных: {e}")
    })?;
    info!("✅ Пул базы данных создан");

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

fn stop_pg(app: &AppHandle) {
    info!("Остановка PostgreSQL...");
    if let Some(guard) = app.try_state::<PgGuard>() {
        let state = guard.0.clone();
        async_runtime::block_on(async move {
            if let Some(pg) = state.lock().await.take() {
                if let Err(e) = pg.stop().await {
                    error!("Ошибка остановки PostgreSQL: {}", e);
                } else {
                    info!("✅ PostgreSQL остановлен");
                }
            }
        });
    }
}

fn main() {
    let _log_guard = setup_logging();
    info!("=== 🚀 Запуск Tauri приложения ===");
    info!("Лог старта пишется в файл: {}", log_file_path().display());

    let pg_state: Arc<Mutex<Option<PostgreSQL>>> = Arc::new(Mutex::new(None));
    let setup_state = pg_state.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(PgGuard(pg_state))
        .manage(commands::ListenerState::default())
        .manage(commands::PlaybackState::default())
        .invoke_handler(tauri::generate_handler![
            commands::play_payload,
            commands::send_file,
            commands::stop_playing,
            commands::start_listening,
            commands::stop_listening
        ])
        .setup(move |app| {
            info!("Настройка приложения...");
            let handle = app.handle().clone();
            let state = setup_state.clone();
            async_runtime::spawn(async move {
                if let Err(e) = bring_up(handle.clone(), state).await {
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
                stop_pg(app_handle);
                info!("✅ Приложение завершено");
            }
        });
}