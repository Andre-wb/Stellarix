use sqlx::{SqlitePool, sqlite::SqliteConnectOptions, Executor};
use sqlx::migrate::Migrator;
use std::path::PathBuf;
use uuid::Uuid;
use crate::schemas::{User, RegisterForm};

pub type DbPool = SqlitePool;
pub static MIGRATOR: Migrator = sqlx::migrate!("./migrations/sqlite");

pub async fn init_pool(db_path: PathBuf) -> Result<DbPool, String> {
    let db_url = format!("sqlite:{}?mode=rwc", db_path.display());

    let options = SqliteConnectOptions::new()
        .filename(&db_path)
        .create_if_missing(true);

    let pool = SqlitePool::connect_with(options)
        .await
        .map_err(|e| format!("Не удалось создать пул SQLite: {e}"))?;

    println!("Запуск миграций SQLite");
    MIGRATOR.run(&pool)
        .await
        .map_err(|e| format!("Не удалось выполнить миграции SQLite: {e}"))?;

    println!("База данных SQLite готова");
    Ok(pool)
}

pub async fn user_exists(pool: &DbPool, username: &str) -> Result<bool, sqlx::Error> {
    let query = "SELECT EXISTS(SELECT 1 FROM users WHERE username = $1)";
    let result: (bool,) = sqlx::query_as(query)
        .bind(username)
        .fetch_one(pool)
        .await?;
    Ok(result.0)
}

pub async fn create_user(
    pool: &DbPool,
    username: &str,
    password_hash: &str,
) -> Result<User, sqlx::Error> {
    let query = "
        INSERT INTO users (id, username, password_hash, created_at, last_login_at)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP, NULL)
        RETURNING id, username, password_hash, created_at, last_login_at
    ";

    let user = sqlx::query_as::<_, User>(query)
        .bind(Uuid::now_v7())
        .bind(username)
        .bind(password_hash)
        .fetch_one(pool)
        .await?;

    Ok(user)
}

pub async fn get_user_by_username(
    pool: &DbPool,
    username: &str,
) -> Result<Option<User>, sqlx::Error> {
    let query = "
        SELECT id, username, password_hash, created_at, last_login_at
        FROM users
        WHERE username = $1
        LIMIT 1
    ";

    let user = sqlx::query_as::<_, User>(query)
        .bind(username)
        .fetch_optional(pool)
        .await?;

    Ok(user)
}

pub async fn get_user_by_id(pool: &DbPool, user_id: Uuid) -> Result<Option<User>, sqlx::Error> {
    let query = "
        SELECT id, username, password_hash, created_at, last_login_at
        FROM users
        WHERE id = $1
    ";

    let user = sqlx::query_as::<_, User>(query)
        .bind(user_id)
        .fetch_optional(pool)
        .await?;

    Ok(user)
}

pub async fn update_last_login(pool: &DbPool, user_id: Uuid) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = $1")
        .bind(user_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub fn validate_registration(form: &RegisterForm) -> Result<(), String> {
    // Та же логика, что и в db.rs
    if form.username.len() < 3 {
        return Err("Имя пользователя должно быть не менее 3 символов".to_string());
    }
    if form.username.len() > 30 {
        return Err("Имя пользователя должно быть менее 30 символов".to_string());
    }
    if !form.username.chars().all(|c| c.is_alphanumeric() || c == '_') {
        return Err("Имя пользователя может содержать только латинские буквы, цифры и подчеркивание".to_string());
    }

    if form.password.len() < 8 {
        return Err("Пароль должен быть не менее 8 символов".to_string());
    }
    if !form.password.chars().any(|c| c.is_uppercase()) {
        return Err("Пароль должен содержать как минимум одну заглавную букву".to_string());
    }
    if !form.password.chars().any(|c| c.is_lowercase()) {
        return Err("Пароль должен содержать как минимум одну строчную букву".to_string());
    }
    if !form.password.chars().any(|c| c.is_numeric()) {
        return Err("Пароль должен содержать как минимум одну цифру".to_string());
    }

    if form.password != form.confirm_password {
        return Err("Пароли не совпадают".to_string());
    }

    Ok(())
}

// Функции хеширования пароля (те же)
pub fn hash_password(password: &str) -> Result<String, String> {
    use argon2::{
        password_hash::{rand_core::OsRng, SaltString, PasswordHasher},
        Argon2,
    };
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();
    argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| format!("Ошибка хеширования: {e}"))
        .map(|hash| hash.to_string())
}

pub fn verify_password(password: &str, hash: &str) -> Result<bool, String> {
    use argon2::{
        password_hash::{PasswordHash, PasswordVerifier},
        Argon2,
    };
    let parsed_hash = PasswordHash::new(hash)
        .map_err(|e| format!("Некорректный хеш: {e}"))?;
    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed_hash)
        .is_ok())
}