use chrono::{DateTime, Utc};
use serde::Deserialize;
use sqlx::FromRow;

use crate::schemas::SessionStats;

pub const KIND_TX: &str = "tx";
pub const KIND_RX: &str = "rx";
pub const KIND_KEY: &str = "key";

pub const NO_VALUE: &str = "—";

pub fn is_valid_kind(kind: &str) -> bool {
    matches!(kind, KIND_TX | KIND_RX | KIND_KEY)
}

pub fn kind_label(kind: &str) -> &str {
    match kind {
        KIND_TX => "Исходящая",
        KIND_RX => "Входящая",
        KIND_KEY => "Обмен ключами",
        other => other,
    }
}

#[derive(Debug, Deserialize)]
pub struct RecordTransferRequest {
    pub kind: String,
    pub ok: bool,
    pub bytes: Option<i64>,
    pub ms: Option<i64>,
}

#[derive(Debug, FromRow)]
pub struct TransferRow {
    pub kind: String,
    pub ok: bool,
    pub bytes: Option<i64>,
    pub duration_ms: Option<i64>,
    pub created_at: DateTime<Utc>,
}

pub struct UserStats {
    pub total_sent: i64,
    pub total_received: i64,
    pub success_rate: String,
    pub average_speed: String,
    pub sessions: Vec<SessionStats>,
    pub sessions_json: String,
}

impl UserStats {
    pub fn empty() -> Self {
        Self {
            total_sent: 0,
            total_received: 0,
            success_rate: NO_VALUE.to_string(),
            average_speed: NO_VALUE.to_string(),
            sessions: Vec::new(),
            sessions_json: "[]".to_string(),
        }
    }
}
