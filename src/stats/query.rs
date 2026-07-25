use chrono::Local;
use uuid::Uuid;

use crate::db::DbPool;
use crate::schemas::SessionStats;

use super::model::{kind_label, TransferRow, UserStats, KIND_RX, KIND_TX, NO_VALUE};

const WINDOW: i64 = 100;

pub async fn user_stats(pool: &DbPool, user_id: Uuid) -> Result<UserStats, sqlx::Error> {
    let rows = sqlx::query_as::<_, TransferRow>(
        "SELECT kind, ok, bytes, duration_ms, created_at
         FROM transfer_stats
         WHERE user_id = $1
         ORDER BY created_at DESC
         LIMIT $2"
    )
        .bind(user_id)
        .bind(WINDOW)
        .fetch_all(pool)
        .await?;

    let mut total_sent = 0;
    let mut total_received = 0;
    let mut ok_count = 0;
    let mut speeds = Vec::new();
    let mut sessions = Vec::with_capacity(rows.len());

    for row in &rows {
        match row.kind.as_str() {
            KIND_TX => total_sent += 1,
            KIND_RX => total_received += 1,
            _ => {}
        }
        if row.ok {
            ok_count += 1;
            if let Some(speed) = speed_bps(row.bytes, row.duration_ms) {
                speeds.push(speed);
            }
        }
        sessions.push(to_session(row));
    }

    let success_rate = if rows.is_empty() {
        NO_VALUE.to_string()
    } else {
        format!("{:.0}%", (ok_count as f64 / rows.len() as f64) * 100.0)
    };

    let average_speed = if speeds.is_empty() {
        NO_VALUE.to_string()
    } else {
        format!("{:.0}", speeds.iter().sum::<f64>() / speeds.len() as f64)
    };

    let sessions_json = serde_json::to_string(&sessions)
        .unwrap_or_else(|_| "[]".to_string())
        .replace('<', "\\u003c");

    Ok(UserStats {
        total_sent,
        total_received,
        success_rate,
        average_speed,
        sessions,
        sessions_json,
    })
}

fn speed_bps(bytes: Option<i64>, duration_ms: Option<i64>) -> Option<f64> {
    match (bytes, duration_ms) {
        (Some(bytes), Some(duration_ms)) if bytes > 0 && duration_ms > 0 => {
            Some((bytes * 8) as f64 * 1000.0 / duration_ms as f64)
        }
        _ => None,
    }
}

fn format_duration(duration_ms: i64) -> String {
    if duration_ms >= 1000 {
        format!("{:.1} с", duration_ms as f64 / 1000.0).replace('.', ",")
    } else {
        format!("{duration_ms} мс")
    }
}

fn to_session(row: &TransferRow) -> SessionStats {
    SessionStats {
        time: row.created_at.with_timezone(&Local).format("%d.%m %H:%M:%S").to_string(),
        session_type: kind_label(&row.kind).to_string(),
        volume: match row.bytes {
            Some(bytes) if bytes >= 0 => format!("{bytes} Б"),
            _ => NO_VALUE.to_string(),
        },
        duration: match row.duration_ms {
            Some(duration_ms) if duration_ms > 0 => format_duration(duration_ms),
            _ => NO_VALUE.to_string(),
        },
        speed: match speed_bps(row.bytes, row.duration_ms) {
            Some(speed) => format!("{speed:.0} бит/с"),
            None => NO_VALUE.to_string(),
        },
        status: if row.ok { "Успешно" } else { "Ошибка" }.to_string(),
        ok: row.ok,
        at: row.created_at.timestamp_millis(),
        kind: row.kind.clone(),
        bytes: row.bytes,
        ms: row.duration_ms,
    }
}
