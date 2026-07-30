pub mod config;
pub mod db_sqlite;
pub mod routes;
pub mod schemas;
pub mod middleware;
pub mod stats;
mod chats;

pub use config::Config;
pub use db_sqlite::DbPool;
pub use routes::*;
pub use schemas::*;

use axum::{
    body::Body,
    http::{header, StatusCode, Uri},
    response::{IntoResponse, Response},
};
use include_dir::{include_dir, Dir};
use std::net::SocketAddr;

/// Статические файлы (CSS/JS) встраиваются в бинарник на этапе компиляции.
/// Это делает раздачу статики одинаковой на десктопе и на Android — не нужно
/// искать каталог на диске (на Android бандл-ресурсы лежат внутри APK как
/// assets, а не как обычные файлы, поэтому раздача через ServeDir там не
/// работала).
static STATIC_ASSETS: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/static");

async fn serve_embedded_static(uri: Uri) -> impl IntoResponse {
    let path = uri.path().trim_start_matches("/static/");

    match STATIC_ASSETS.get_file(path) {
        Some(file) => {
            let mime = mime_guess::from_path(path).first_or_octet_stream();
            Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, mime.as_ref())
                .header(header::CACHE_CONTROL, "no-cache")
                .body(Body::from(file.contents()))
                .unwrap()
        }
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

pub async fn create_router(pool: DbPool) -> axum::Router {
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
        .route("/static/*path", get(serve_embedded_static))
        .with_state(pool)
}

pub async fn serve(
    pool: DbPool,
    addr: SocketAddr,
    is_production: bool,
) -> Result<(), String> {
    let listener = tokio::net::TcpListener::bind(addr).await
        .map_err(|e| format!("Не удалось привязаться к адресу {addr}: {e}"))?;
    serve_on(listener, pool, is_production).await
}

pub async fn serve_on(
    listener: tokio::net::TcpListener,
    pool: DbPool,
    is_production: bool,
) -> Result<(), String> {
    use tower_sessions::{cookie::SameSite, Expiry, SessionManagerLayer};
    use tower_sessions_memory_store::MemoryStore;
    use time::Duration;

    let session_store = MemoryStore::default();

    let same_site = if is_production { SameSite::Strict } else { SameSite::Lax };
    let session_layer = SessionManagerLayer::new(session_store)
        .with_secure(is_production)
        .with_http_only(true)
        .with_same_site(same_site)
        .with_expiry(Expiry::OnInactivity(Duration::hours(24)));

    let app = create_router(pool).await.layer(session_layer);

    axum::serve(listener, app).await
        .map_err(|e| format!("Ошибка сервера: {e}"))?;

    Ok(())
}