use axum::{
    response::Response,
    middleware::Next,
    extract::Request,
};
use tower_sessions::Session;

pub async fn inject_auth_context(
    mut request: Request,
    next: Next,
) -> Response {
    let session = request.extensions().get::<Session>().cloned();
    let logged_in = if let Some(session) = session {
        session.get::<String>("user_id")
            .await
            .ok()
            .flatten()
            .is_some()
    } else {
        false
    };

    request.extensions_mut().insert(logged_in);
    next.run(request).await
}