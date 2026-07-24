use argon2::{
    password_hash::{
        rand_core::OsRng,
        PasswordHash,
        SaltString,
        PasswordVerifier,
        PasswordHasher,
    },
    Argon2,
};
use sqlx::{PgPool, Postgres, migrate::{Migrator, MigrateDatabase}};
use crate::schemas::{RegisterForm, User};
use uuid::Uuid;

pub type DbPool = PgPool;
pub static MIGRATOR: Migrator = sqlx::migrate!();

pub async fn init_pool() -> Result<DbPool, String> {
    let database_url = crate::config::database_url();
    println!("Подключение к базе данных: {}", database_url);

    if !Postgres::database_exists(database_url).await.unwrap_or(false) {
        Postgres::create_database(database_url)
            .await
            .map_err(|error| format!("Не удалось создать базу данных: {error}"))?;
    }

    let pool = PgPool::connect(database_url)
        .await
        .map_err(|error| format!("Не удалось создать пул подключений к базе данных: {error}"))?;
    println!("Запуск миграций базы данных");

    MIGRATOR.run(&pool)
        .await
        .map_err(|error| format!("Не удалось выполнить миграции базы данных: {error}"))?;

    println!("База данных готова к работе");
    Ok(pool)
}

/// Проверка уникальности имени пользователя
pub async fn user_exists(
    pool: &DbPool,
    username: &str,
) -> Result<bool, sqlx::Error> {
    let query = "SELECT EXISTS(SELECT 1 FROM users WHERE username = $1)";

    let (exists,): (bool,) = sqlx::query_as(query)
        .bind(username)
        .fetch_one(pool)
        .await?;

    Ok(exists)
}

/// Добавление пользователя в базу данных
pub async fn create_user(
    pool: &DbPool,
    username: &str,
    password_hash: &str,
) -> Result<User, sqlx::Error> {
    let query = "
        INSERT INTO users (username, password_hash, created_at)
        VALUES ($1, $2, NOW())
        RETURNING id, username, password_hash, created_at, last_login_at
    ";

    let user = sqlx::query_as::<_, User>(query)
        .bind(username)
        .bind(password_hash)
        .fetch_one(pool)
        .await?;

    Ok(user)
}

/// Поиск пользователя по имени
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

/// Валидация логина и надежности пароля (без email-проверок)
pub fn validate_registration(form: &RegisterForm) -> Result<(), String> {
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

pub fn hash_password(password: &str) -> Result<String, String> {
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();
    let password_hash = argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|error| format!("Ошибка хеширования пароля: {error}"))?
        .to_string();

    Ok(password_hash)
}

pub fn verify_password(password: &str, hash: &str) -> Result<bool, String> {
    let parsed_hash = PasswordHash::new(hash)
        .map_err(|error| format!("Некорректный формат хеша: {error}"))?;
    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed_hash)
        .is_ok()
    )
}

pub async fn get_user_by_id(pool: &DbPool, user_id: Uuid) -> Result<Option<User>, sqlx::Error> {
    let user = sqlx::query_as::<_, User>(
        "SELECT id, username, password_hash, created_at, last_login_at FROM users WHERE id = $1"
    )
        .bind(user_id)
        .fetch_optional(pool)
        .await?;

    Ok(user)
}

pub async fn update_last_login(pool: &DbPool, user_id: Uuid) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE users SET last_login_at = NOW() WHERE id = $1")
        .bind(user_id)
        .execute(pool)
        .await?;
    Ok(())
}