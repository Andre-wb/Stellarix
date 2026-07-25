pub mod config;
pub mod db;
pub mod routes;
pub mod schemas;
pub mod middleware;
pub mod stats;

pub use config::Config;
pub use db::DbPool;
pub use routes::*;
pub use schemas::*;

use axum::http::{header, HeaderValue};
use tower_http::services::ServeDir;
use tower_http::set_header::SetResponseHeaderLayer;
use std::net::SocketAddr;
use std::path::PathBuf;

pub async fn create_router(pool: DbPool, static_dir: PathBuf) -> axum::Router {
    use axum::{Router, routing::{get, post}};
    use routes::{
        get_profile, get_login, post_login,
        get_register, post_register, logout,
        get_pairing, get_chat, get_dashboard, get_settings,
    };

    Router::new()
        .route("/", get(get_register))
        .route("/register", get(get_register))
        .route("/register", post(post_register))
        .route("/login", get(get_login))
        .route("/login", post(post_login))
        .route("/profile", get(get_profile))
        .route("/logout", get(logout))
        .route("/pairing", get(get_pairing))
        .route("/chat", get(get_chat))
        .route("/dashboard", get(get_dashboard))
        .route("/settings", get(get_settings))
        .route("/api/stats", post(stats::record_transfer))
        .route("/diagnostics", get(get_diagnostics))
        .nest_service(
            "/static",
            Router::new()
                .fallback_service(ServeDir::new(static_dir))
                .layer(SetResponseHeaderLayer::overriding(
                    header::CACHE_CONTROL,
                    HeaderValue::from_static("no-cache"),
                )),
        )
        .with_state(pool)
}

pub async fn serve(
    pool: DbPool,
    addr: SocketAddr,
    static_dir: PathBuf,
    is_production: bool,
) -> Result<(), String> {
    let listener = tokio::net::TcpListener::bind(addr).await
        .map_err(|e| format!("Не удалось привязаться к адресу {addr}: {e}"))?;
    serve_on(listener, pool, static_dir, is_production).await
}

pub async fn serve_on(
    listener: tokio::net::TcpListener,
    pool: DbPool,
    static_dir: PathBuf,
    is_production: bool,
) -> Result<(), String> {
    use tower_sessions::{cookie::SameSite, Expiry, SessionManagerLayer};
    use tower_sessions_sqlx_store::PostgresStore;
    use time::Duration;

    let session_store = PostgresStore::new(pool.clone());
    session_store.migrate().await
        .map_err(|e| format!("Не удалось выполнить миграцию хранилища сессий: {e}"))?;

    let same_site = if is_production { SameSite::Strict } else { SameSite::Lax };
    let session_layer = SessionManagerLayer::new(session_store)
        .with_secure(is_production)
        .with_http_only(true)
        .with_same_site(same_site)
        .with_expiry(Expiry::OnInactivity(Duration::hours(24)));

    let app = create_router(pool, static_dir).await.layer(session_layer);

    axum::serve(listener, app).await
        .map_err(|e| format!("Ошибка сервера: {e}"))?;

    Ok(())
}