use dotenvy::dotenv;
use std::env;
use std::sync::OnceLock;
pub use crate::schemas::Config;

static CONFIG: OnceLock<Config> = OnceLock::new();

impl Config {
    pub fn init() -> Result<&'static Config, String> {
        dotenv().ok();

        let config = Config {
            username_secret: leak_string(get_env("USERNAME_SECRET")?),
            session_secret: leak_string(get_env("SESSION_SECRET")?),
            database_url: leak_string(get_env("DATABASE_URL")?),
            app_environment: leak_string(get_env("APP_ENVIRONMENT")?),
            log_level: leak_string(get_env("LOG_LEVEL")?),
        };

        config.validate()?;

        CONFIG.set(config)
            .map_err(|_| "Не удалось установить глобальную конфигурацию".to_string())?;

        Ok(CONFIG.get().unwrap())
    }

    pub fn global() -> &'static Config {
        match CONFIG.get() {
            Some(config) => config,
            None => {
                eprintln!("ОШИБКА: Конфигурация не инициализирована. Сначала вызовите Config::init()");
                std::process::exit(1);
            }
        }
    }

    fn validate(&self) -> Result<(), String> {
        if self.username_secret.is_empty() {
            return Err("USERNAME_SECRET не может быть пустым".to_string());
        }

        if self.session_secret.is_empty() {
            return Err("SESSION_SECRET не может быть пустым".to_string());
        }

        Ok(())
    }

    pub fn is_production(&self) -> bool {
        self.app_environment.eq_ignore_ascii_case("production")
    }
}

fn get_env(key: &str) -> Result<String, String> {
    env::var(key).map_err(|_| format!("Переменная окружения {} не задана", key))
}

fn leak_string(s: String) -> &'static str {
    Box::leak(Box::new(s))
}

pub fn database_url() -> &'static str {
    Config::global().database_url
}