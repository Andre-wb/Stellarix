use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::Path;

use argon2::password_hash::rand_core::{OsRng, RngCore};
use percent_encoding::{utf8_percent_encode, NON_ALPHANUMERIC};

const ENV_PATH: &str = ".env";

pub fn ensure_env_file() -> Result<bool, String> {
    if Path::new(ENV_PATH).exists() {
        return Ok(false);
    }

    println!("Файл .env не найден. Запускается первичная настройка.");

    let db_host = prompt("Хост базы данных", "localhost")?;
    let db_port = prompt("Порт базы данных", "5432")?;
    let db_name = prompt("Имя базы данных", "stellarix")?;
    let default_user = env::var("USER").unwrap_or_else(|_| "postgres".to_string());
    let db_user = prompt("Пользователь базы данных", &default_user)?;
    let db_password = prompt("Пароль базы данных (пусто — без пароля)", "")?;
    let app_environment = prompt("Окружение", "development")?;
    let log_level = prompt("Уровень логирования", "info")?;

    let database_url = build_database_url(&db_user, &db_password, &db_host, &db_port, &db_name);

    let contents = format!(
        "USERNAME_SECRET={}\nSESSION_SECRET={}\nDATABASE_URL={}\nAPP_ENVIRONMENT={}\nLOG_LEVEL={}\n",
        random_secret(),
        random_secret(),
        database_url,
        app_environment,
        log_level,
    );

    fs::write(ENV_PATH, contents).map_err(|error| format!("Не удалось записать .env: {error}"))?;
    println!("Файл .env создан.");

    Ok(true)
}

fn prompt(label: &str, default: &str) -> Result<String, String> {
    if default.is_empty() {
        print!("{label}: ");
    } else {
        print!("{label} [{default}]: ");
    }
    io::stdout().flush().map_err(|error| error.to_string())?;

    let mut input = String::new();
    io::stdin()
        .read_line(&mut input)
        .map_err(|error| error.to_string())?;

    let trimmed = input.trim();
    if trimmed.is_empty() {
        Ok(default.to_string())
    } else {
        Ok(trimmed.to_string())
    }
}

fn build_database_url(user: &str, password: &str, host: &str, port: &str, name: &str) -> String {
    let user_encoded = utf8_percent_encode(user, NON_ALPHANUMERIC).to_string();
    if password.is_empty() {
        format!("postgres://{user_encoded}@{host}:{port}/{name}")
    } else {
        let password_encoded = utf8_percent_encode(password, NON_ALPHANUMERIC).to_string();
        format!("postgres://{user_encoded}:{password_encoded}@{host}:{port}/{name}")
    }
}

fn random_secret() -> String {
    let mut buffer = [0u8; 32];
    OsRng.fill_bytes(&mut buffer);
    buffer.iter().map(|byte| format!("{:02x}", byte)).collect()
}
