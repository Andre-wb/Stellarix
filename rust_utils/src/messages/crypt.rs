use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use aes_gcm::{
    aead::{Aead, AeadCore, KeyInit, OsRng},
    Aes256Gcm,
    Key,
    Nonce,
};
use std::string::String;

/// AES-256-GCM защита
/// Пример использования на Python:
///
/// import vortex_chat
/// key = vortex_chat.generate_key()
///
/// encrypted_message = vortex_chat.encrypt_message("message", key)
/// decrypted_message = vortex_chat.decrypt_message(encrypted_message, key)


/// AES-256-GCM зашифровка
#[pyfunction]
pub fn encrypt_message(message: Vec<u8>, key: Vec<u8>) -> PyResult<Vec<u8>> {
    if key.len() != 32 {
        return Err(PyValueError::new_err("Ключ должен быть длиной в 32 бита"));
    }

    let key = Key::<Aes256Gcm>::from_slice(&key);
    let cipher = Aes256Gcm::new(key);

    let nonce = Aes256Gcm::generate_nonce(&mut OsRng);

    let ciphertext = cipher
        .encrypt(&nonce, message.as_ref())
        .map_err(|_| PyValueError::new_err("Зашифровка не удалась"))?;

    let mut result = nonce.to_vec();
    result.extend_from_slice(&ciphertext);

    Ok(result)
}

/// AES-256-GCM расшифровка
#[pyfunction]
pub fn decrypt_message(encrypted: Vec<u8>, key: Vec<u8>) -> PyResult<String> {
    if key.len() != 32 {
        return Err(PyValueError::new_err("Ключ должен быть длиной в 32 бита"));
    }

    if encrypted.len() < 12 {
        return Err(PyValueError::new_err("Шифр слишком короткий"));
    }

    let (nonce_bytes, ciphertext) = encrypted.split_at(12);
    let nonce = Nonce::from_slice(nonce_bytes);

    let key = Key::<Aes256Gcm>::from_slice(&key);
    let cipher = Aes256Gcm::new(key);
    
    let plaintext = String::from_utf8(
        cipher
        .decrypt(nonce, ciphertext)
        .map_err(|_| PyValueError::new_err(
            "Ошибка при расшифровке или при проверке интеграции"
        ))?
    ).map_err(|e| PyValueError::new_err(format!("Некорректная UTF-8 последовательность: {}", e)));


    plaintext
}