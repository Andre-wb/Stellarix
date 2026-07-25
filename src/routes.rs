use axum::{
    response::{Html, Redirect},
    extract::State,
    Form, Json,
};
use askama::Template;
use tower_sessions::Session;
use uuid::Uuid;
use crate::db::{self, verify_password, hash_password, DbPool};
use crate::stats::UserStats;
use crate::schemas::{
    LoginTemplate,
    UserProfileTemplate,
    RegisterForm,
    RegisterTemplate,
    LoginForm,
    PairingTemplate,
    ChatTemplate,
    DashboardTemplate,
};

const SESSION_USER_ID: &str = "user_id";

async fn is_logged_in(session: &Session) -> bool {
    session.get::<String>(SESSION_USER_ID)
        .await
        .ok()
        .flatten()
        .is_some()
}

pub async fn session_user_id(session: &Session) -> Option<Uuid> {
    let raw = session.get::<String>(SESSION_USER_ID).await.ok().flatten()?;
    Uuid::parse_str(&raw).ok()
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

pub async fn get_dashboard(
    session: Session,
    State(pool): State<DbPool>,
) -> Result<Html<String>, Redirect> {
    let user_id = match session_user_id(&session).await {
        Some(id) => id,
        None => return Err(Redirect::to("/login")),
    };

    let user = match db::get_user_by_id(&pool, user_id).await {
        Ok(Some(user)) => user,
        _ => return Err(Redirect::to("/login")),
    };

    // Статистика для таблиц о пользователе
    let stats = match crate::stats::user_stats(&pool, user_id).await {
        Ok(stats) => stats,
        Err(e) => {
            tracing::error!("Ошибка получения статистики: {}", e);
            UserStats::empty()
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
        sessions: stats.sessions,
        sessions_json: stats.sessions_json,
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