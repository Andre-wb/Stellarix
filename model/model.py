import io
from os import path

import numpy as np
import scipy.io.wavfile as wav
from joblib import load
from scipy import signal
from scipy.ndimage import gaussian_filter1d

FS = 48000  # частота дискретизации
N_FFT = 4096  # размер окна
HOP_LENGTH = 1024  # шаг окна

BASE_DIR = path.dirname(path.abspath(__file__))
model_path = path.join(BASE_DIR, 'remove_noise_model.pkl')

# Модель загружается один раз при импорте модуля,
# чтобы не грузить её заново на каждый запрос
model = load(model_path)


def bytes_to_audio(audio_bytes: bytes) -> np.ndarray:
    """Превращает сырые байты WAV (тело запроса) в массив float32."""
    sr, data = wav.read(io.BytesIO(audio_bytes))
    if data.dtype == np.int16:
        data = data / 32768.0
    elif data.dtype == np.int32:
        data = data / 2147483648.0
    return data.astype(np.float32)


def audio_to_bytes(audio: np.ndarray) -> bytes:
    """Превращает массив float32 обратно в байты WAV для ответа."""
    buf = io.BytesIO()
    audio_int16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
    wav.write(buf, FS, audio_int16)
    return buf.getvalue()


def audio_to_stft(audio):  # превращение аудио в спектрограмму быстрым преобразованием Фурье
    f, t, Zxx = signal.stft(
        audio, fs=FS, nperseg=N_FFT, noverlap=N_FFT - HOP_LENGTH
    )
    return f, t, np.abs(Zxx), np.angle(Zxx), Zxx


def stft_to_audio(magnitude, phase):  # превращение спектрограммы в аудио
    Zxx = magnitude * np.exp(1j * phase)
    _, audio = signal.istft(
        Zxx, fs=FS, nperseg=N_FFT, noverlap=N_FFT - HOP_LENGTH
    )
    return audio


def extract_features(mag_noisy):  # извлекает признаки из спектрограммы
    n_freqs, n_frames = mag_noisy.shape

    padded = np.pad(
        mag_noisy, ((1, 1), (1, 1)), mode='constant', constant_values=0
    )

    f_center = padded[1:-1, 1:-1]
    f_top = padded[0:-2, 1:-1]
    f_bottom = padded[2:, 1:-1]
    t_left = padded[1:-1, 0:-2]
    t_right = padded[1:-1, 2:]

    tl = padded[0:-2, 0:-2]
    tr = padded[0:-2, 2:]
    bl = padded[2:, 0:-2]
    br = padded[2:, 2:]

    local_mean = (
                         f_center + f_top + f_bottom + t_left + t_right + tl + tr + bl + br
                 ) / 9.0
    local_diff = f_center - local_mean  # если >0, скорее всего это полезный сигнал, если ~0, то сливается с окружением

    features = np.column_stack([
        f_center.flatten(),
        f_top.flatten(),
        f_bottom.flatten(),
        t_left.flatten(),
        t_right.flatten(),
        tl.flatten(),
        tr.flatten(),
        bl.flatten(),
        br.flatten(),
        local_mean.flatten(),
        local_diff.flatten(),
    ])  # сборка признаков в список

    return features


def denoise_audio(audio: np.ndarray) -> np.ndarray:
    """Прогоняет аудио (numpy-массив) через модель и возвращает очищенный сигнал."""
    f, t, mag_noisy, phase_noisy, _ = audio_to_stft(audio)

    features = extract_features(mag_noisy)
    pred_mask_flat = model.predict(features)  # вектор значений маски
    pred_mask = pred_mask_flat.reshape(mag_noisy.shape)  # сворачивает вектор в матрицу размера mag_noisy

    pred_mask = gaussian_filter1d(pred_mask, sigma=0.8, axis=0)  # сглаживает значения
    pred_mask = np.clip(pred_mask, 0.0, 1.0)

    clean_mag = mag_noisy * pred_mask  # поэлементное умножение
    clean_audio = stft_to_audio(clean_mag, phase_noisy)  # обратное преобразование Фурье

    return clean_audio


def process_request(audio_bytes: bytes) -> bytes:
    """
    Точка входа для внешнего запроса (например, с Rust-сервера):
    принимает сырые байты WAV, возвращает байты очищенного WAV.
    Никакой работы с файлами на диске — всё происходит в памяти.
    """
    audio = bytes_to_audio(audio_bytes)
    clean_audio = denoise_audio(audio)
    return audio_to_bytes(clean_audio)