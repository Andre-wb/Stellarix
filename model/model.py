from glob import glob
from os import path, remove
from joblib import dump
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import scipy.io.wavfile as wav
from scipy.ndimage import gaussian_filter1d
from sklearn.ensemble import HistGradientBoostingRegressor

FS = 48000 #частота дискретизации
N_FFT = 4096 #размер окна
HOP_LENGTH = 1024 #шаг окна

BAND_LOW_HZ = 1000.0 #нижняя граница полезного сигнала
BAND_HIGH_HZ = 7000.0 #верхняя граница полезного сигнала
FREQ_RES = FS / N_FFT #шаг
BIN_LOW = int(np.round(BAND_LOW_HZ / FREQ_RES)) #начало диапазона
BIN_HIGH = int(np.round(BAND_HIGH_HZ / FREQ_RES)) #конец

BASE_DIR = path.dirname(path.abspath(__file__)) #директории
clean_dir = path.join(BASE_DIR, 'dataset', 'train', 'clean')
noisy_dir = path.join(BASE_DIR, 'dataset', 'train', 'noisy')
model_path = path.join(BASE_DIR, 'remove_noise_model.pkl')


def load_wav(filepath): #загрузка звука
    sr, data = wav.read(filepath)
    if data.dtype == np.int16:
        data = data / 32768.0
    elif data.dtype == np.int32:
        data = data / 2147483648.0
    return data.astype(np.float32)


def audio_to_stft(audio): #превращение аудио в спектограмму быстрым преобразованием фурье
    f, t, Zxx = signal.stft(
        audio, fs=FS, nperseg=N_FFT, noverlap=N_FFT - HOP_LENGTH
    )
    return f, t, np.abs(Zxx), np.angle(Zxx), Zxx


def stft_to_audio(magnitude, phase): #превращение спектограммы в аудио
    Zxx = magnitude * np.exp(1j * phase)
    _, audio = signal.istft(
        Zxx, fs=FS, nperseg=N_FFT, noverlap=N_FFT - HOP_LENGTH
    )
    return audio


def extract_features(mag_noisy): #извлекает признаки из спектограммы
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
    local_diff = f_center - local_mean #если >0, скорее всего это полезный сигнал, если ~0, то сливается с окружением


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
    ]) #сборка признаков в список

    return features


def prepare_dataset(clean_dir, noisy_dir, max_files=40): #подготовка датасета для обучения
    X_list, Y_list = [], []
    noisy_files = sorted(glob(path.join(noisy_dir, '*.wav')))[:max_files]

    for noisy_path in noisy_files:
        fname = path.basename(noisy_path)
        clean_path = path.join(clean_dir, fname)

        clean_audio = load_wav(clean_path)
        noisy_audio = load_wav(noisy_path)

        _, _, mag_clean, _, _ = audio_to_stft(clean_audio) #извлечение громкости
        _, _, mag_noisy, _, _ = audio_to_stft(noisy_audio)

        #Винеровское оценивание
        noise_density = 1e-8 #спектральная плотность мощности шума чтобы не происходило деление на 0
        target_mask = (mag_clean ** 2) / (mag_noisy ** 2 + noise_density) #mag_clean**2 - спектральная плотность мощности полезного сигнала, mag_noisy**2 - спектральная плотность мощности шума
        target_mask = np.clip(target_mask, 0.05, 1.0)

        features = extract_features(mag_noisy)
        X_list.append(features)
        Y_list.append(target_mask.flatten())

    X = np.vstack(X_list)
    Y = np.concatenate(Y_list)
    return X, Y


def denoise_audio_file(model, noisy_path, output_path): #очистка файла и его загрузка
    noisy_audio = load_wav(noisy_path)
    f, t, mag_noisy, phase_noisy, _ = audio_to_stft(noisy_audio)

    features = extract_features(mag_noisy)
    pred_mask_flat = model.predict(features) #вектор значений маски
    pred_mask = pred_mask_flat.reshape(mag_noisy.shape) #сворачивает вектор в матрицу размера mag_noisy

    pred_mask = gaussian_filter1d(pred_mask, sigma=0.8, axis=0) #сглаживает значения
    pred_mask = np.clip(pred_mask, 0.0, 1.0)

    clean_mag = mag_noisy * pred_mask #поэлементное умножение
    clean_audio = stft_to_audio(clean_mag, phase_noisy) #обратное преобразование фурье

    clean_audio_int16 = np.int16(np.clip(clean_audio, -1.0, 1.0) * 32767)
    wav.write(output_path, FS, clean_audio_int16)

    return clean_audio, mag_noisy, clean_mag

def circular_phase_error(phase_a, phase_b): #вычисление MSE (среднеквадратическая ошибка)
    """Вычисление MSE"""
    diff = np.angle(np.exp(1j * (phase_a - phase_b))) #Перевод разности на комплексную окружность, использую формулу эйлера
    return np.mean(diff ** 2)


#Оценка качества модели
def calculate_dataset_accuracy(model, clean_dir, noisy_dir, max_test_files=50):
    noisy_files = sorted(glob(path.join(noisy_dir, '*.wav')))[:max_test_files]

    mse_before_list, mse_after_list = [], []
    phase_err_before_list, phase_err_after_list = [], []

    for noisy_path in noisy_files:
        fname = path.basename(noisy_path)
        clean_path = path.join(clean_dir, fname)

        clean_audio = load_wav(clean_path)
        noisy_audio = load_wav(noisy_path)

        out_tmp = path.join(BASE_DIR, 'tmp.wav')
        pred_audio, _, _ = denoise_audio_file(model, noisy_path, out_tmp)
        if path.exists(out_tmp):
            remove(out_tmp)

        min_len = min(len(clean_audio), len(pred_audio), len(noisy_audio))
        clean_audio = clean_audio[:min_len]
        noisy_audio = noisy_audio[:min_len]
        pred_audio = pred_audio[:min_len]

        #Считает среднеквадратичную ошибку и SSNR
        mse_before_list.append(np.mean((clean_audio - noisy_audio) ** 2))
        mse_after_list.append(np.mean((clean_audio - pred_audio) ** 2))

        #Проверка фазы
        _, _, _, ph_clean, _ = audio_to_stft(clean_audio)
        _, _, _, ph_noisy, _ = audio_to_stft(noisy_audio)
        _, _, _, ph_pred, _ = audio_to_stft(pred_audio)

        #1-7 кГц
        ph_clean_band = ph_clean[BIN_LOW:BIN_HIGH, :]
        ph_noisy_band = ph_noisy[BIN_LOW:BIN_HIGH, :]
        ph_pred_band = ph_pred[BIN_LOW:BIN_HIGH, :]

        phase_err_before_list.append(circular_phase_error(ph_clean_band, ph_noisy_band))
        phase_err_after_list.append(circular_phase_error(ph_clean_band, ph_pred_band))

    avg_mse_before = np.mean(mse_before_list)
    avg_mse_after = np.mean(mse_after_list)
    total_improvement = ((avg_mse_before - avg_mse_after) / avg_mse_before) * 100 #На сколько процентов упала ошибка
    snr_db_gain = 10 * np.log10(avg_mse_before / avg_mse_after) #прирост дБ

    avg_ph_err_before = np.mean(phase_err_before_list)
    avg_ph_err_after = np.mean(phase_err_after_list)


    print('Результаты:')
    print(' ' * 60)
    print(f'• Средняя ошибка до фильтрации (MSE):   {avg_mse_before:.6f}')
    print(f'• Средняя ошибка после фильтрации (MSE): {avg_mse_after:.6f}')
    print(f'• Снижение уровня шума / ошибки:        {total_improvement:.2f}%')
    print(f'• Прирост дБ: +{snr_db_gain:.2f} дБ')
    print(' ' * 60)
    print(f'• Фазовая ошибка до фильтрации:   {avg_ph_err_before:.6f}')
    print(f'• Фазовая ошибка после фильтрации: {avg_ph_err_after:.6f}')

if __name__ == '__main__':
    print('Подготовка обучающей выборки ...')
    X_train, Y_train = prepare_dataset(clean_dir, noisy_dir, max_files=40)

    if X_train is not None:
        print('Обучение модели (HistGradientBoosting) ...')
        model = HistGradientBoostingRegressor(
            max_iter=300,
            max_depth=10,
            learning_rate=0.08,
            l2_regularization=1.0,
            random_state=42,
        )
        model.fit(X_train, Y_train)
        print('Модель успешно обучена!!')

        print('Расчет точности ...')
        calculate_dataset_accuracy(model, clean_dir, noisy_dir, max_test_files=40)

        dump(model, model_path)
        print(f'Обученная модель сохранена в файл {model_path}')