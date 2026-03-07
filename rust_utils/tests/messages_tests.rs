use pyo3::{
    prelude::*,
};
use vortex_chat::{hash_message, generate_key, encrypt_message, decrypt_message,  ChatStats};
#[cfg(test)]
mod tests {
    use tokio::time::Instant;
    use super::*;

    ///  Проверка лимита ключа
    #[test]
    fn test_generating() -> PyResult<()> {
        let key = generate_key()?;
        assert_eq!(key.len(), 32, "Ключ должен весить 32 бита");
        Ok(())
    }

    /// Проверка лимита хэша
    #[test]
    fn test_hashing() -> PyResult<()> {
        let message = Vec::new();
        let hash = hash_message(message)?;
        assert_eq!(hash.len(), 32, "Хэш должен весить 32 бита");

        Ok(())
    }

    /// Проверка зашифровки и расшифровки сообщений
    #[test]
    fn test_message_encrypting() -> PyResult<()> {
        let message = Vec::new();
        let key = generate_key()?;
        let encrypted = encrypt_message(message.clone(), key.clone())?;
        assert!(encrypted.len() > message.len(), "Зашифрованные данные должны быть длиннее оригинала");

        let decrypted = decrypt_message(encrypted, key)?;
        assert_eq!(decrypted.as_bytes(), message, "Расшифрованные данные должны совпадать с оригиналом");

        Ok(())
    }

    #[test]
    fn test_tampering_detection() -> PyResult<()> {
        let key = generate_key()?;
        let message = "message".as_bytes().to_vec();
        let encrypted = encrypt_message(message, key.clone())?;

        let tampered = Vec::new();
        let result = decrypt_message(tampered, key);
        assert!(result.is_err(), "Подделанные данные должны вызвать ошибку расшифровки");

        let wrong_key = generate_key()?;
        let result = decrypt_message(encrypted, wrong_key);
        assert!(result.is_err(), "Неправильный ключ должен вызвать ошибку расшифровки");

        Ok(())
    }

    #[test]
    fn test_determinism() -> PyResult<()> {

        let key = generate_key()?;
        let message = "message".as_bytes().to_vec();

        // Идентичные сообщения не должны иметь идентичные шифры
        let encrypted1 = encrypt_message(message.clone(), key.clone())?;
        let encrypted2 = encrypt_message(message, key.clone())?;

        assert_ne!(encrypted1, encrypted2, "Идентичные сообщения должны иметь разные шифры");

        // Идентичные сообщения должны идентично расшифровываться
        let decrypted1 = decrypt_message(encrypted1, key.clone())?;
        let decrypted2 = decrypt_message(encrypted2, key)?;

        assert_eq!(decrypted1.as_bytes(), decrypted2.as_bytes());
        assert_eq!(decrypted1.as_bytes(), b"message");
        assert_ne!(decrypted1.as_bytes(), b"wrong message");

        Ok(())

    }

    /// Статистика чата
    #[test]
    fn test_chat_stats() {
        let mut stats = ChatStats::new();
        assert_eq!(stats.get_stats(), "Сообщений: 0, обработано: 0 KB");

        stats.add_message(1024);
        assert_eq!(stats.get_stats(), "Сообщений: 1, обработано: 1 KB");

        stats.add_message(2048);
        assert_eq!(stats.get_stats(), "Сообщений: 2, обработано: 3 KB");
    }


    /// Тест производительности
    #[test]
    fn test_performance() -> PyResult<()> {
        pyo3::prepare_freethreaded_python();

        let key = generate_key()?;
        let message_sizes = [64, 1024, 16384, 65536];
        let iterations = 100;

        for &size in &message_sizes {
            // Сообщение только из ASCII символов (0-127)
            let message: Vec<u8> = (0..size).map(|i| (i % 128) as u8).collect();

            // Зашифровка
            let start = Instant::now();
            let mut encrypted_vec = Vec::with_capacity(iterations);
            for _ in 0..iterations {
                let encrypted = encrypt_message(message.clone(), key.clone())?;
                encrypted_vec.push(encrypted);
            }
            let encrypt_duration = start.elapsed();

            // Расшифровка
            let start = Instant::now();
            for encrypted in &encrypted_vec {
                let _ = decrypt_message(encrypted.clone(), key.clone())?;
            }
            let decrypt_duration = start.elapsed();

            let encrypt_throughput = (size * iterations) as f64 / encrypt_duration.as_secs_f64() / 1_000_000.0;
            let decrypt_throughput = (size * iterations) as f64 / decrypt_duration.as_secs_f64() / 1_000_000.0;

            println!("Размер {} байт:", size);
            println!("  Зашифровка: {:?} для {} ops ({:.2} MB/s)",
                     encrypt_duration, iterations, encrypt_throughput);
            println!("  Расшифровка: {:?} для {} ops ({:.2} MB/s)",
                     decrypt_duration, iterations, decrypt_throughput);
        }

        Ok(())
    }

    /// Тест конкурентности
    #[test]
    fn test_concurrent_usage() -> PyResult<()> {
        pyo3::prepare_freethreaded_python();

        use std::thread;

        let handles: Vec<_> = (0..4).map(|_| {
            thread::spawn(move || {
                let key = generate_key()?;
                let message = Vec::new();

                for _ in 0..10 {
                    let encrypted = encrypt_message(message.clone(), key.clone())?;
                    let decrypted = decrypt_message(encrypted.clone(), key.clone())?;
                    assert_eq!(decrypted.as_bytes(), message);
                }

                Ok::<(), PyErr>(())
            })
        }).collect();

        for handle in handles {
            let _ = handle.join().unwrap();
        }

        Ok(())
    }

    /// Тест чата
    #[test]
    fn test_full_chat_flow() -> PyResult<()> {
        pyo3::prepare_freethreaded_python();

        let key = generate_key()?;
        let mut stats = ChatStats::new();

        let messages = vec![
            "Привет!",
            "Как дела?",
            "Что делаешь?"
        ];

        let mut encrypted_history = Vec::new();

        for msg in messages.clone() {
            let encrypted = encrypt_message(msg.as_bytes().to_vec(), key.clone())?;
            stats.add_message(msg.len());
            encrypted_history.push(encrypted);
        }

        assert_eq!(stats.get_stats(), "Сообщений: 3, обработано: 0 KB");

        for (i, encrypted) in encrypted_history.iter().enumerate() {
            let decrypted = decrypt_message(encrypted.clone(), key.clone())?;
            assert_eq!(decrypted.as_bytes(), messages[i].as_bytes());
        }

        Ok(())
    }
}