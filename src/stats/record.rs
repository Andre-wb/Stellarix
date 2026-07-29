use axum::{extract::State, http::StatusCode, Json};
use tower_sessions::Session;

use crate::db_sqlite::DbPool;
use crate::routes::session_user_id;

use super::model::{is_valid_kind, RecordTransferRequest};

pub async fn record_transfer(
    State(pool): State<DbPool>,
    session: Session,
    Json(request): Json<RecordTransferRequest>,
) -> Result<StatusCode, StatusCode> {
    let user_id = session_user_id(&session).await.ok_or(StatusCode::UNAUTHORIZED)?;

    if !is_valid_kind(&request.kind) {
        return Err(StatusCode::BAD_REQUEST);
    }

    sqlx::query(
        "INSERT INTO transfer_stats (user_id, kind, ok, bytes, duration_ms)
         VALUES ($1, $2, $3, $4, $5)"
    )
        .bind(user_id)
        .bind(&request.kind)
        .bind(request.ok)
        .bind(request.bytes.filter(|value| *value >= 0))
        .bind(request.ms.filter(|value| *value > 0))
        .execute(&pool)
        .await
        .map_err(|error| {
            tracing::error!("Не удалось сохранить телеметрию передачи: {}", error);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    Ok(StatusCode::NO_CONTENT)
}
