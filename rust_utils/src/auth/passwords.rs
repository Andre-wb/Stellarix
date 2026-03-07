use pyo3::prelude::*;
use argon2::{password_hash::{PasswordHasher, PasswordVerifier, SaltString, rand_core::OsRng}, Argon2, PasswordHash};

/// Хэширование пароля
#[pyfunction]
pub fn hash_password(password: &str) -> PyResult<String> {
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();

    let password_hash = argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|_| PyErr::new::<pyo3::exceptions::PyValueError, _>("Хэширование не удалось"))?
        .to_string();

    Ok(password_hash)
}

/// Верификация пароля
/// Пример использования на Python:
///
/// import vortex_chat
/// hashed = vortex_chat.hash_password("password")
/// vortex_chat.verify_password("password", hashed)
#[pyfunction]
pub fn verify_password(password: &str, hash: &str) -> PyResult<bool> {
    let parsed_hash = PasswordHash::new(hash)
        .map_err(|_| PyErr::new::<pyo3::exceptions::PyValueError, _>("Некорректный формат хэша"))?;

    let argon2 = Argon2::default();

    Ok(argon2.verify_password(password.as_bytes(), &parsed_hash).is_ok())
}