use stellarix::db;
use stellarix::config;
use stellarix::setup;
use std::net::SocketAddr;
use std::path::PathBuf;

#[tokio::main]
async fn main() {
    let generated_env = match setup::ensure_env_file() {
        Ok(generated) => generated,
        Err(error) => {
            eprintln!("Не удалось подготовить конфигурацию окружения: {error}");
            std::process::exit(1);
        }
    };
    dotenvy::dotenv().ok();
    if let Err(error) = config::Config::init() {
        eprintln!("Не удалось инициализировать конфигурацию: {error}");
        std::process::exit(1);
    }

    let config = config::Config::global();

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| config.log_level.into())
        )
        .init();

    let pool = match db::init_pool().await {
        Ok(pool) => pool,
        Err(error) => {
            if generated_env {
                let _ = std::fs::remove_file(".env");
            }
            eprintln!("{error}");
            std::process::exit(1);
        }
    };

    let addr = SocketAddr::from(([127, 0, 0, 1], 8000));
    tracing::info!("Сервер запущен и ожидает соединений на {}", addr);

    if let Err(e) = stellarix::serve(pool, addr, PathBuf::from("static"), config.is_production()).await {
        if generated_env {
            let _ = std::fs::remove_file(".env");
        }
        tracing::error!("{}", e);
        std::process::exit(1);
    }
}