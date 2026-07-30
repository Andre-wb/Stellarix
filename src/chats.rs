use axum::{
    extract::{Path, State},
    http::StatusCode,
    Json,
};
use serde::Deserialize;
use tower_sessions::Session;
use uuid::Uuid;
use crate::db_sqlite::DbPool;
use crate::routes::session_user_id;
use crate::schemas::{Chat, Message};

const MAX_PAYLOAD_HEX_LEN: usize = 512;

#[derive(Deserialize, Debug)]
pub struct CreateChatRequest {
    pub peer_fingerprint: String,
}

#[derive(Deserialize, Debug)]
pub struct CreateMessageRequest {
    pub payload_hex: String,
    pub outgoing: bool,
}

fn is_hex(value: &str) -> bool {
    !value.is_empty()
        && value.len() % 2 == 0
        && value.chars().all(|c| c.is_ascii_hexdigit())
}

async fn require_user(session: &Session) -> Result<Uuid, StatusCode> {
    session_user_id(session).await.ok_or(StatusCode::UNAUTHORIZED)
}

fn internal_error(error: sqlx::Error) -> StatusCode {
    tracing::error!("Ошибка базы данных в API чатов: {}", error);
    StatusCode::INTERNAL_SERVER_ERROR
}

pub async fn list_chats(
    State(pool): State<DbPool>,
    session: Session,
) -> Result<Json<Vec<Chat>>, StatusCode> {
    let user_id = require_user(&session).await?;

    let chats = sqlx::query_as::<_, Chat>(
        "SELECT id, owner_id, peer_fingerprint, created_at
         FROM chats
         WHERE owner_id = $1
         ORDER BY created_at"
    )
        .bind(user_id)
        .fetch_all(&pool)
        .await
        .map_err(internal_error)?;

    Ok(Json(chats))
}

pub async fn create_chat(
    State(pool): State<DbPool>,
    session: Session,
    Json(request): Json<CreateChatRequest>,
) -> Result<Json<Chat>, StatusCode> {
    let user_id = require_user(&session).await?;

    if !is_hex(&request.peer_fingerprint) || request.peer_fingerprint.len() > 64 {
        return Err(StatusCode::BAD_REQUEST);
    }

    let chat = sqlx::query_as::<_, Chat>(
        "INSERT INTO chats (owner_id, peer_fingerprint)
         VALUES ($1, $2)
         ON CONFLICT (owner_id, peer_fingerprint)
         DO UPDATE SET peer_fingerprint = EXCLUDED.peer_fingerprint
         RETURNING id, owner_id, peer_fingerprint, created_at"
    )
        .bind(user_id)
        .bind(request.peer_fingerprint.to_lowercase())
        .fetch_one(&pool)
        .await
        .map_err(internal_error)?;

    Ok(Json(chat))
}

pub async fn list_messages(
    State(pool): State<DbPool>,
    session: Session,
    Path(chat_id): Path<Uuid>,
) -> Result<Json<Vec<Message>>, StatusCode> {
    let user_id = require_user(&session).await?;

    let owns_chat: (bool,) = sqlx::query_as(
        "SELECT EXISTS(SELECT 1 FROM chats WHERE id = $1 AND owner_id = $2)"
    )
        .bind(chat_id)
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .map_err(internal_error)?;
    if !owns_chat.0 {
        return Err(StatusCode::NOT_FOUND);
    }

    let messages = sqlx::query_as::<_, Message>(
        "SELECT id, chat_id, outgoing, payload_hex, sent_at
         FROM messages
         WHERE chat_id = $1
         ORDER BY sent_at"
    )
        .bind(chat_id)
        .fetch_all(&pool)
        .await
        .map_err(internal_error)?;

    Ok(Json(messages))
}

pub async fn create_message(
    State(pool): State<DbPool>,
    session: Session,
    Path(chat_id): Path<Uuid>,
    Json(request): Json<CreateMessageRequest>,
) -> Result<Json<Message>, StatusCode> {
    let user_id = require_user(&session).await?;

    if !is_hex(&request.payload_hex) || request.payload_hex.len() > MAX_PAYLOAD_HEX_LEN {
        return Err(StatusCode::BAD_REQUEST);
    }

    let message = sqlx::query_as::<_, Message>(
        "INSERT INTO messages (chat_id, outgoing, payload_hex)
         SELECT $1, $2, $3
         WHERE EXISTS(SELECT 1 FROM chats WHERE id = $1 AND owner_id = $4)
         RETURNING id, chat_id, outgoing, payload_hex, sent_at"
    )
        .bind(chat_id)
        .bind(request.outgoing)
        .bind(request.payload_hex.to_lowercase())
        .bind(user_id)
        .fetch_optional(&pool)
        .await
        .map_err(internal_error)?;

    match message {
        Some(message) => Ok(Json(message)),
        None => Err(StatusCode::NOT_FOUND),
    }
}
