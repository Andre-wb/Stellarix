use pyo3::prelude::*;
use blake3;
use aes_gcm::{
    aead::{
        KeyInit,
        OsRng
    },
    Aes256Gcm,
};

/// Хэширование сообщений
#[pyfunction]
pub fn hash_message(message: Vec<u8>) -> PyResult<Vec<u8>> {
    let hash: Vec<u8> = blake3::hash(&message).as_bytes().to_vec();
    Ok(hash)
}

/// Генерация случайного секретного ключа
#[pyfunction]
pub fn generate_key() -> PyResult<Vec<u8>> {
    let key = Aes256Gcm::generate_key(&mut OsRng);
    Ok(key.to_vec())
}