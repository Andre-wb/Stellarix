use axum::{
    response::{Html, Redirect},
    extract::State,
    Form, Json,
};
use askama::Template;
use tower_sessions::Session;
use uuid::Uuid;
use chrono::{DateTime, Utc};
use crate::db::{self, verify_password, hash_password, DbPool};
use crate::schemas::{
    LoginTemplate,
    UserProfileTemplate,
    RegisterForm,
    RegisterTemplate,
    LoginForm,
    PairingTemplate,
    ChatTemplate,
    DashboardTemplate,
    SessionStats,
};

const SESSION_USER_ID: &str = "user_id";

async fn is_logged_in(session: &Session) -> bool {
    session.get::<String>(SESSION_USER_ID)
        .await
        .ok()
        .flatten()
        .is_some()
}

pub async fn get_register(session: Session) -> Html<String> {
    if is_logged_in(&session).await {
        return Html("<script>window.location.href='/profile'</script>".to_string());
    }

    Html(RegisterTemplate {
        flash_message: None,
        username: None,
        password: None,
        confirm_password: None,
        logged_in: false,
    }.render().unwrap())
}

pub async fn get_login(session: Session) -> Html<String> {
    if is_logged_in(&session).await {
        return Html("<script>window.location.href='/profile'</script>".to_string());
    }

    Html(LoginTemplate {
        flash_message: None,
        username: None,
        password: None,
        logged_in: false,
    }.render().unwrap())
}

pub async fn get_profile(
    session: Session,
    State(pool): State<DbPool>,
) -> Result<Html<String>, Redirect> {
    let user_id = match session.get::<String>(SESSION_USER_ID).await.ok().flatten() {
        Some(id) => id,
        None => return Err(Redirect::to("/login")),
    };

    let user_id = match Uuid::parse_str(&user_id) {
        Ok(id) => id,
        Err(_) => return Err(Redirect::to("/login")),
    };

    let user = match db::get_user_by_id(&pool, user_id).await {
        Ok(Some(user)) => user,
        _ => return Err(Redirect::to("/login")),
    };

    let avatar_letter = user
        .username
        .chars()
        .next()
        .map(|c| c.to_uppercase().to_string())
        .unwrap_or_else(|| "U".to_string());

    Ok(Html(UserProfileTemplate {
        user,
        avatar_letter,
        logged_in: true,
    }.render().unwrap()))
}

pub async fn logout(session: Session) -> Html<String> {
    session.remove::<String>(SESSION_USER_ID).await.ok();
    Html("<!doctype html><meta charset=\"utf-8\"><script>try{['e2ee_priv_jwk','e2ee_pub_hex','e2ee_session_hex','e2ee_fingerprint'].forEach(function(k){localStorage.removeItem(k)})}catch(e){}location.replace('/login')</script>".to_string())
}

pub async fn post_register(
    State(pool): State<DbPool>,
    session: Session,
    Form(form): Form<RegisterForm>,
) -> Result<Redirect, Html<String>> {
    if let Err(error_message) = db::validate_registration(&form) {
        let error_html = RegisterTemplate {
            flash_message: Some(error_message),
            username: Some(form.username.clone()),
            password: Some(form.password.clone()),
            confirm_password: Some(form.confirm_password.clone()),
            logged_in: false,
        }.render().unwrap();
        return Err(Html(error_html));
    }

    match db::user_exists(&pool, &form.username).await {
        Ok(true) => {
            let error_html = RegisterTemplate {
                flash_message: Some("Пользователь с таким именем уже существует".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                confirm_password: Some(form.confirm_password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        }
        Err(error) => {
            tracing::error!("Ошибка базы данных: {}", error);
            let error_html = RegisterTemplate {
                flash_message: Some("Внутренняя ошибка базы данных. Попробуйте позже.".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                confirm_password: Some(form.confirm_password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        },
        Ok(false) => {}
    }

    let password_hash = match hash_password(&form.password) {
        Ok(hash) => hash,
        Err(error) => {
            tracing::error!("Не удалось создать хеш: {}", error);
            let error_html = RegisterTemplate {
                flash_message: Some("Ошибка безопасности при регистрации".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                confirm_password: Some(form.confirm_password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        }
    };

    let user = match db::create_user(&pool, &form.username, &password_hash).await {
        Ok(user) => user,
        Err(error) => {
            tracing::error!("Не удалось создать запись пользователя: {}", error);
            let error_html = RegisterTemplate {
                flash_message: Some("Ошибка добавления пользователя в базу".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                confirm_password: Some(form.confirm_password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        }
    };

    if let Err(error) = complete_login(&pool, &session, user.id).await {
        tracing::error!("Ошибка авторизации после регистрации: {}", error);
    }

    Ok(Redirect::to("/profile"))
}

pub async fn post_login(
    State(pool): State<DbPool>,
    session: Session,
    Form(form): Form<LoginForm>,
) -> Result<Redirect, Html<String>> {
    let user = match db::get_user_by_username(&pool, &form.username).await {
        Ok(Some(user)) => user,
        Ok(None) => {
            let error_html = LoginTemplate {
                flash_message: Some("Неверное имя пользователя или пароль".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        },
        Err(error) => {
            tracing::error!("Ошибка базы данных: {}", error);
            let error_html = LoginTemplate {
                flash_message: Some("Ошибка авторизации. Попробуйте еще раз".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        }
    };

    match verify_password(&form.password, &user.password_hash) {
        Ok(true) => {}
        Ok(false) => {
            let error_html = LoginTemplate {
                flash_message: Some("Неверное имя пользователя или пароль".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        }
        Err(error) => {
            tracing::error!("Ошибка верификации пароля: {}", error);
            let error_html = LoginTemplate {
                flash_message: Some("Внутренняя ошибка криптографии.".to_string()),
                username: Some(form.username.clone()),
                password: Some(form.password.clone()),
                logged_in: false,
            }.render().unwrap();
            return Err(Html(error_html));
        }
    }

    if let Err(error) = complete_login(&pool, &session, user.id).await {
        tracing::error!("Ошибка завершения сессии входа: {}", error);
        let error_html = LoginTemplate {
            flash_message: Some("Ошибка сессии во время входа.".to_string()),
            username: Some(form.username.clone()),
            password: Some(form.password.clone()),
            logged_in: false,
        }.render().unwrap();
        return Err(Html(error_html));
    }

    Ok(Redirect::to("/profile"))
}

async fn complete_login(
    pool: &DbPool,
    session: &Session,
    user_id: Uuid,
) -> Result<(), String> {
    db::update_last_login(pool, user_id).await
        .map_err(|e| e.to_string())?;
    session.insert(SESSION_USER_ID, user_id.to_string()).await
        .map_err(|e| e.to_string())?;

    Ok(())
}

pub async fn get_pairing(
    session: Session,
    State(pool): State<DbPool>,
) -> Result<Html<String>, Redirect> {
    let user_id = match session.get::<String>(SESSION_USER_ID).await.ok().flatten() {
        Some(id) => id,
        None => return Err(Redirect::to("/login")),
    };

    let user_id = match Uuid::parse_str(&user_id) {
        Ok(id) => id,
        Err(_) => return Err(Redirect::to("/login")),
    };

    let user = match db::get_user_by_id(&pool, user_id).await {
        Ok(Some(user)) => user,
        _ => return Err(Redirect::to("/login")),
    };

    Ok(Html(PairingTemplate {
        logged_in: true,
        username: user.username,
    }.render().unwrap()))
}

pub async fn get_chat(
    session: Session,
    State(pool): State<DbPool>,
) -> Result<Html<String>, Redirect> {
    let user_id = match session.get::<String>(SESSION_USER_ID).await.ok().flatten() {
        Some(id) => id,
        None => return Err(Redirect::to("/login")),
    };

    let user_id = match Uuid::parse_str(&user_id) {
        Ok(id) => id,
        Err(_) => return Err(Redirect::to("/login")),
    };

    let user = match db::get_user_by_id(&pool, user_id).await {
        Ok(Some(user)) => user,
        _ => return Err(Redirect::to("/login")),
    };

    Ok(Html(ChatTemplate {
        logged_in: true,
        username: user.username,
    }.render().unwrap()))
}

// Структура для хранения статистики пользователя
#[derive(Default)]
struct UserStats {
    total_sent: i64,
    total_received: i64,
    success_rate: String,
    average_speed: String,
    speed_chart_data: String,
    result_chart_data: String,
    duration_chart_data: String,
    bytes_chart_data: String,
    sessions: Vec<SessionStats>,
}

// Функция для получения статистики пользователя
async fn get_user_stats(pool: &DbPool, user_id: Uuid) -> Result<UserStats, String> {
    use sqlx::Row;

    // Получаем все чаты пользователя
    let chats = sqlx::query(
        r#"
        SELECT id FROM chats
        WHERE owner_id = $1
        "#
    )
        .bind(user_id)
        .fetch_all(pool)
        .await
        .map_err(|e| e.to_string())?;

    let mut chat_ids = Vec::new();
    for row in chats {
        let id: Uuid = row.try_get("id").map_err(|e| e.to_string())?;
        chat_ids.push(id);
    }

    let mut total_sent = 0;
    let mut total_received = 0;
    let mut speed_data = Vec::new();
    let mut duration_data = Vec::new();
    let mut bytes_data = Vec::new();
    let mut session_stats = Vec::new();

    // Если есть чаты, получаем сообщения
    if !chat_ids.is_empty() {
        // Получаем все сообщения пользователя
        let messages = sqlx::query(
            r#"
            SELECT chat_id, outgoing, payload_hex, sent_at
            FROM messages
            WHERE chat_id = ANY($1)
            ORDER BY sent_at DESC
            LIMIT 100
            "#
        )
            .bind(&chat_ids)
            .fetch_all(pool)
            .await
            .map_err(|e| e.to_string())?;

        // Считаем статистику по сообщениям
        for row in messages {
            let outgoing: bool = row.try_get("outgoing").map_err(|e| e.to_string())?;
            let payload_hex: String = row.try_get("payload_hex").map_err(|e| e.to_string())?;
            let sent_at: DateTime<Utc> = row.try_get("sent_at").map_err(|e| e.to_string())?;

            let payload_bytes = hex::decode(&payload_hex).unwrap_or_default();
            let size_bytes = payload_bytes.len() as i64;

            if outgoing {
                total_sent += 1;
                // Генерируем фиктивные данные для демонстрации
                let speed = (size_bytes * 8) as f64 / 0.5;
                speed_data.push(speed);
                duration_data.push(0.5);
                bytes_data.push(size_bytes);

                session_stats.push(SessionStats {
                    time: sent_at.format("%H:%M:%S").to_string(),
                    session_type: "Исходящая".to_string(),
                    volume: format!("{} Б", size_bytes),
                    duration: "0.5с".to_string(),
                    speed: format!("{:.0} бит/с", speed),
                    status: "Успешно".to_string(),
                });
            } else {
                total_received += 1;
                let speed = (size_bytes * 8) as f64 / 0.7;
                speed_data.push(speed);
                duration_data.push(0.7);
                bytes_data.push(size_bytes);

                session_stats.push(SessionStats {
                    time: sent_at.format("%H:%M:%S").to_string(),
                    session_type: "Входящая".to_string(),
                    volume: format!("{} Б", size_bytes),
                    duration: "0.7с".to_string(),
                    speed: format!("{:.0} бит/с", speed),
                    status: "Успешно".to_string(),
                });
            }
        }
    }

    // Вычисляем дополнительные метрики
    let total_messages = total_sent + total_received;
    let success_rate = if total_messages > 0 {
        format!("{:.1}%", (total_sent as f64 / total_messages as f64) * 100.0)
    } else {
        "—".to_string()
    };

    let avg_speed = if !speed_data.is_empty() {
        let avg = speed_data.iter().sum::<f64>() / speed_data.len() as f64;
        format!("{:.0}", avg)
    } else {
        "—".to_string()
    };

    // Подготавливаем данные для графиков
    let speed_chart: Vec<f64> = speed_data.iter().rev().take(20).cloned().collect();
    let duration_chart: Vec<f64> = duration_data.iter().rev().take(12).cloned().collect();
    let bytes_chart: Vec<i64> = bytes_data.iter().rev().take(12).cloned().collect();

    let success_count = total_sent + total_received;
    let error_count = 0;

    Ok(UserStats {
        total_sent,
        total_received,
        success_rate,
        average_speed: avg_speed,
        speed_chart_data: serde_json::to_string(&speed_chart).unwrap_or_else(|_| "[]".to_string()),
        result_chart_data: serde_json::to_string(&vec![success_count, error_count]).unwrap_or_else(|_| "[0,0]".to_string()),
        duration_chart_data: serde_json::to_string(&duration_chart).unwrap_or_else(|_| "[]".to_string()),
        bytes_chart_data: serde_json::to_string(&bytes_chart).unwrap_or_else(|_| "[]".to_string()),
        sessions: session_stats,
    })
}

pub async fn get_dashboard(
    session: Session,
    State(pool): State<DbPool>,
) -> Result<Html<String>, Redirect> {
    let user_id = match session.get::<String>(SESSION_USER_ID).await.ok().flatten() {
        Some(id) => id,
        None => return Err(Redirect::to("/login")),
    };

    let user_id = match Uuid::parse_str(&user_id) {
        Ok(id) => id,
        Err(_) => return Err(Redirect::to("/login")),
    };

    let user = match db::get_user_by_id(&pool, user_id).await {
        Ok(Some(user)) => user,
        _ => return Err(Redirect::to("/login")),
    };

    // Статистика для таблиц о пользователе
    let stats = match get_user_stats(&pool, user_id).await {
        Ok(stats) => stats,
        Err(e) => {
            tracing::error!("Ошибка получения статистики: {}", e);
            UserStats::default()
        }
    };

    let has_sessions = !stats.sessions.is_empty();

    Ok(Html(DashboardTemplate {
        logged_in: true,
        username: user.username,
        total_messages_sent: stats.total_sent,
        total_messages_received: stats.total_received,
        success_rate: stats.success_rate,
        average_speed: stats.average_speed,
        speed_chart_data: stats.speed_chart_data,
        result_chart_data: stats.result_chart_data,
        duration_chart_data: stats.duration_chart_data,
        bytes_chart_data: stats.bytes_chart_data,
        sessions: stats.sessions,
        has_sessions,
    }.render().unwrap()))
}

pub async fn get_diagnostics(
    session: Session,
) -> Json<serde_json::Value> {
    use serde_json::json;

    Json(json!({
        "is_authenticated": session.get::<String>(SESSION_USER_ID).await.ok().flatten().is_some(),
    }))
}