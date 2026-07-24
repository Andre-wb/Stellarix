use askama::Template;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow};
use uuid::Uuid;

#[derive(Debug, FromRow, Clone)]
pub struct User {
    pub id: Uuid,
    pub username: String,
    pub password_hash: String,
    pub created_at: DateTime<Utc>,
    pub last_login_at: Option<DateTime<Utc>>,
}

#[derive(Debug, FromRow, Clone, Serialize)]
pub struct Chat {
    pub id: Uuid,
    pub owner_id: Uuid,
    pub peer_fingerprint: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, FromRow, Clone, Serialize)]
pub struct Message {
    pub id: Uuid,
    pub chat_id: Uuid,
    pub outgoing: bool,
    pub payload_hex: String,
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