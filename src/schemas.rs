use askama::Template;
use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde::Serialize;
use sqlx::{FromRow};
use uuid::Uuid;

#[derive(Debug, FromRow, Clone)]
pub struct User {
    pub id: Uuid,
    pub username: String,
    #[sqlx(skip)]
    pub avatar_url: String,
    pub password_hash: String,
    pub created_at: DateTime<Utc>,
    pub last_login_at: Option<DateTime<Utc>>,
    #[sqlx(skip)]
    pub chats: Vec<Chat>,
}

#[derive(Debug, FromRow, Clone)]
pub struct Chat {
    pub members: Vec<User>,
    pub messages: Vec<Message>,
    pub session_key: String,
}

#[derive(Debug, FromRow, Clone)]
pub struct Message {
    pub id: Uuid,
    pub author: User,
    pub content: String,
    pub sent_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub username_secret: &'static str,
    pub session_secret: &'static str,
    pub database_url: &'static str,
    pub app_environment: &'static str,
    pub log_level: &'static str,
}

#[derive(Template)]
#[template(path = "register.html")]
pub struct RegisterTemplate {
    pub flash_message: Option<String>,
    pub username: Option<String>,
    pub password: Option<String>,
    pub confirm_password: Option<String>,
    pub logged_in: bool,
}

#[derive(Template)]
#[template(path = "login.html")]
pub struct LoginTemplate {
    pub flash_message: Option<String>,
    pub username: Option<String>,
    pub password: Option<String>,
    pub logged_in: bool,
}

#[derive(Template)]
#[template(path = "profile.html")]
pub struct UserProfileTemplate {
    pub user: User,
    pub avatar_letter: String,
    pub logged_in: bool,
}

#[derive(Template)]
#[template(path = "pairing.html")]
pub struct PairingTemplate {
    pub logged_in: bool,
    pub username: String,
}

#[derive(Template)]
#[template(path = "chat.html")]
pub struct ChatTemplate {
    pub logged_in: bool,
    pub username: String,
}

// Структура для статистики сессий
#[derive(Debug, Clone, Serialize)]
pub struct SessionStats {
    pub time: String,
    pub session_type: String,
    pub volume: String,
    pub duration: String,
    pub speed: String,
    pub status: String,
}

#[derive(Template)]
#[template(path = "dashboard.html")]
pub struct DashboardTemplate {
    pub logged_in: bool,
    pub username: String,
    pub total_messages_sent: i64,
    pub total_messages_received: i64,
    pub success_rate: String,
    pub average_speed: String,
    pub speed_chart_data: String,
    pub result_chart_data: String,
    pub duration_chart_data: String,
    pub bytes_chart_data: String,
    pub sessions: Vec<SessionStats>,
    pub has_sessions: bool,
}

#[derive(Deserialize, Debug)]
pub struct RegisterForm {
    pub username: String,
    pub password: String,
    pub confirm_password: String,
}

#[derive(Deserialize, Debug)]
pub struct LoginForm {
    pub username: String,
    pub password: String,
}