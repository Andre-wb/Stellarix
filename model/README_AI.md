Complex U-Net Audio Denoiser
Система шумоподавления для звуковых сигналов на основе комплексной сверточной сети ComplexUNetDenoiser (PyTorch). Модель работает со спектрограммами (STFT), обрабатывая вещественную и мнимую части сигнала в выделенной частотной полосе. Проект поддерживает интеграцию с бэкендом на Rust через обработку WAV-байтов в оперативной памяти.

🛠 Технические параметры сигнала
Частота дискретизации (FS): 48 000 Гц

Размер окна FFT (N_FFT): 5120

Рабочая полоса частот: бины 107–747 (ориентировочно 1–7 кГц)

Размер патча для обучения (CROP_FRAMES): 64 OFDM-символа / кадра

Масштабирование (SCALE_FACTOR): 100.0 (для числовой стабильности PyTorch)

🚀 Использование через CLI
Скрипт поддерживает управление через аргументы командной строки.

1. Обучение модели (train)
Обучает сеть ComplexUNetDenoiser с использованием L1Loss и адаптивного оптимизатора AdamW + ReduceLROnPlateau. По окончании веса сохраняются в unet_complex_denoiser.pth, после чего автоматически запускается оценка качества.

Bash
python model.py train --epochs 30 --max-files 3500 --max-test-files 200
--epochs: количество эпох (по умолчанию: 30)

--max-files: лимит файлов из обучающей выборки (по умолчанию: 3500)

--max-test-files: лимит файлов для итоговой оценки (по умолчанию: 200)

2. Оценка качества и метрик (test)
Загружает сохраненную модель unet_complex_denoiser.pth и вычисляет метрики MSE (до/после) и прирост SNR (в дБ) на тестовом датасете.

Bash
python model.py test --max-files 200
3. Очистка одного WAV-файла (denoise)
Убирает шум из указанного файла и сохраняет результат на диск:

Bash
python model.py denoise input_noisy.wav output_clean.wav
🦀 Интеграция с Rust-сервером (FFI)
Модуль предоставляет точку входа process_request(audio_bytes: bytes) -> bytes, которая выполняет обработку аудио напрямую в памяти без промежуточной записи на диск.

Пример вызова из Rust (через PyO3):
Rust
use pyo3::prelude::*;
use pyo3::types::PyBytes;

pub fn denoise_audio_bytes(input_wav: &[u8]) -> PyResult<Vec<u8>> {
    Python::with_gil(|py| {
        let model_module = PyModule::import(py, "model")?;
        let py_bytes = PyBytes::new(py, input_wav);
        
        let clean_bytes = model_module
            .getattr("process_request")?
            .call1((py_bytes,))?
            .extract::<&[u8]>()?;

        Ok(clean_bytes.to_vec())
    })
}