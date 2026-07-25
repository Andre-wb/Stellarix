import argparse
import io

import os
import glob
import numpy as np
import scipy.io.wavfile as wav
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader


FS = 48000 #частота дискретизации
N_FFT = 5120 #размер окна

FREQ_BIN_START = 107 #нижняя граница
FREQ_BIN_END = 747 #верхняя граница
N_FREQ = FREQ_BIN_END - FREQ_BIN_START #рабочий диапазон

CROP_FRAMES = 64  # Количество OFDM-символов в одном куске для обучения
SCALE_FACTOR = 100.0  # Масштабирующий коэффициент для стабильности PyTorch

base_dir = os.path.dirname(os.path.abspath(__file__))
train_clean_dir = os.path.join(base_dir, 'dataset', 'train', 'clean')
train_noisy_dir = os.path.join(base_dir, 'dataset', 'train', 'noisy')
test_clean_dir = os.path.join(base_dir, 'dataset', 'test', 'clean')
test_noisy_dir = os.path.join(base_dir, 'dataset', 'test', 'noisy')
model_path = os.path.join(base_dir, 'unet_complex_denoiser.pth')
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

_model = None

def load_wav(filepath):
    _, data = wav.read(filepath)
    if data.dtype == np.int16:
        data = data / 32768.0
    elif data.dtype == np.int32:
        data = data / 2147483648.0
    return data.astype(np.float32)

def save_wav(audio: np.ndarray, filepath):
    audio_int16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
    wav.write(filepath, FS, audio_int16)

def bytes_to_audio(audio_bytes: bytes) -> np.ndarray:
    """Преобразует байты WAV из Rust-сервера в numpy-массив float32."""
    _, data = wav.read(io.BytesIO(audio_bytes))
    if data.dtype == np.int16:
        data = data / 32768.0
    elif data.dtype == np.int32:
        data = data / 2147483648.0
    return data.astype(np.float32)

def audio_to_bytes(audio: np.ndarray) -> bytes:
    """Преобразует float32 audio в байты WAV для ответа Rust-серверу."""
    buf = io.BytesIO()
    audio_int16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
    wav.write(buf, FS, audio_int16)
    return buf.getvalue()

def audio_to_complex_stft(audio): #преобразование аудио в спектрограмму
    n_frames = len(audio) // N_FFT
    if n_frames == 0:
        # Если файл короткий, дополняем нулями до N_FFT
        audio = np.pad(audio, (0, N_FFT - len(audio)))
        n_frames = 1

    audio_trimmed = audio[:n_frames * N_FFT]
    frames = audio_trimmed.reshape(n_frames, N_FFT)

    # rfft по строкам
    spectrum = np.fft.rfft(frames, axis=1)
    return spectrum.T  # Транспонируем в shape [Bins, Time]


def complex_stft_to_audio(spectrum): #спектрограмма в аудио
    spectrum_t = spectrum.T  # [Time, Bins]
    frames = np.fft.irfft(spectrum_t, n=N_FFT, axis=1)
    return frames.flatten().astype(np.float32)

class ComplexAudioDataset(Dataset):
    def __init__(self, clean_dir, noisy_dir, max_files=3500):
        self.inputs = []
        self.targets = []

        noisy_files = sorted(glob.glob(os.path.join(noisy_dir, '*.wav')))[:max_files]

        for n_path in noisy_files:
            fname = os.path.basename(n_path)
            c_path = os.path.join(clean_dir, fname)

            if not os.path.exists(c_path):
                continue

            clean_audio = load_wav(c_path)
            noisy_audio = load_wav(n_path)

            min_len = min(len(clean_audio), len(noisy_audio))
            clean_audio, noisy_audio = clean_audio[:min_len], noisy_audio[:min_len]

            stft_clean = audio_to_complex_stft(clean_audio)
            stft_noisy = audio_to_complex_stft(noisy_audio)

            #Вырезаем рабочую полосу частот
            crop_clean = stft_clean[FREQ_BIN_START:FREQ_BIN_END, :]
            crop_noisy = stft_noisy[FREQ_BIN_START:FREQ_BIN_END, :]

            self._add_crops(crop_noisy, crop_clean)

        self.inputs = torch.tensor(np.array(self.inputs), dtype=torch.float32)
        self.targets = torch.tensor(np.array(self.targets), dtype=torch.float32)
        print(f"Обучающих сэмплов (кусочков спектра): {len(self.inputs)}")

    def _add_crops(self, noisy_stft, clean_stft):
        n_frames = noisy_stft.shape[1]

        if n_frames < CROP_FRAMES:
            pad = CROP_FRAMES - n_frames
            noisy_stft = np.pad(noisy_stft, ((0, 0), (0, pad)))
            clean_stft = np.pad(clean_stft, ((0, 0), (0, pad)))
            n_frames = CROP_FRAMES

        step = CROP_FRAMES // 2
        for start in range(0, n_frames - CROP_FRAMES + 1, step):
            end = start + CROP_FRAMES

            # Масштабируем данные
            n_crop = noisy_stft[:, start:end] / SCALE_FACTOR
            c_crop = clean_stft[:, start:end] / SCALE_FACTOR

            n_tensor = np.stack([np.real(n_crop), np.imag(n_crop)], axis=0)
            c_tensor = np.stack([np.real(c_crop), np.imag(c_crop)], axis=0)

            self.inputs.append(n_tensor)
            self.targets.append(c_tensor)

    def __len__(self):
        return len(self.inputs)

    def __getitem__(self, idx):
        return self.inputs[idx], self.targets[idx]

class ComplexUNetDenoiser(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.MaxPool2d(2)

        self.enc1 = self._block(2, 32)
        self.enc2 = self._block(32, 64)
        self.enc3 = self._block(64, 128)
        self.bottleneck = self._block(128, 256)

        self.dec3 = self._block(256 + 128, 128)
        self.dec2 = self._block(128 + 64, 64)
        self.dec1 = self._block(64 + 32, 32)

        self.final = nn.Conv2d(32, 2, kernel_size=1)

    @staticmethod
    def _block(in_c, out_c):
        return nn.Sequential(
            nn.Conv2d(in_c, out_c, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_c),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_c, out_c, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_c),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b = self.bottleneck(self.pool(e3))

        d3 = F.interpolate(b, size=e3.shape[2:], mode='bilinear', align_corners=False)
        d3 = self.dec3(torch.cat([d3, e3], dim=1))

        d2 = F.interpolate(d3, size=e2.shape[2:], mode='bilinear', align_corners=False)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))

        d1 = F.interpolate(d2, size=e1.shape[2:], mode='bilinear', align_corners=False)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))

        return self.final(d1)


def get_model():
    """загрузка модели с кэшированием в памяти"""
    global _model
    if _model is None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Модель не найдена по пути {model_path}"
            )
        model = ComplexUNetDenoiser().to(device)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()
        _model = model
    return _model


def denoise_audio(model, noisy_path):  # убираем шум из аудио
    model.eval()
    noisy_audio = load_wav(noisy_path)
    stft_noisy = audio_to_complex_stft(noisy_audio)

    # Берём только рабочий диапазон
    stft_band = stft_noisy[FREQ_BIN_START:FREQ_BIN_END, :]

    orig_time_frames = stft_band.shape[1]

    # Добавляем паддинг
    pad_time = (8 - (orig_time_frames % 8)) % 8
    if pad_time > 0:
        stft_band = np.pad(stft_band, ((0, 0), (0, pad_time)))

    real_part = np.real(stft_band) / SCALE_FACTOR
    imag_part = np.imag(stft_band) / SCALE_FACTOR

    x_input = np.stack([real_part, imag_part], axis=0)
    x_tensor = torch.tensor(x_input, dtype=torch.float32).unsqueeze(0).to(device)

    with torch.no_grad():
        out_tensor = model(x_tensor).squeeze(0).cpu().numpy()

    clean_real = out_tensor[0][:, :orig_time_frames]
    clean_imag = out_tensor[1][:, :orig_time_frames]

    # Возвращаем масштаб обратно
    complex_clean_band = (clean_real + 1j * clean_imag) * SCALE_FACTOR

    # Зануляем всё вне полосы 1-7 кГц
    full_stft_clean = np.zeros_like(stft_noisy, dtype=np.complex64)
    full_stft_clean[FREQ_BIN_START:FREQ_BIN_END, :] = complex_clean_band

    clean_audio = complex_stft_to_audio(full_stft_clean)
    return clean_audio, noisy_audio

#оценка качества модели
def evaluate(model, clean_dir, noisy_dir, max_test_files=200):
    noisy_files = sorted(glob.glob(os.path.join(noisy_dir, '*.wav')))[:max_test_files]

    mse_before_list, mse_after_list = [], []
    for n_path in noisy_files:
        fname = os.path.basename(n_path)
        c_path = os.path.join(clean_dir, fname)

        if not os.path.exists(c_path):
            continue

        clean_audio = load_wav(c_path)
        pred_audio, noisy_audio = denoise_audio(model, n_path)

        min_len = min(len(clean_audio), len(pred_audio), len(noisy_audio))
        clean_audio = clean_audio[:min_len]
        noisy_audio = noisy_audio[:min_len]
        pred_audio = pred_audio[:min_len]

        mse_before_list.append(np.mean((clean_audio - noisy_audio) ** 2))
        mse_after_list.append(np.mean((clean_audio - pred_audio) ** 2))

    avg_before = np.mean(mse_before_list)
    avg_after = np.mean(mse_after_list)
    improvement = (avg_before - avg_after) / avg_before * 100
    snr_gain = 10 * np.log10(avg_before / (avg_after + 1e-12))

    print('РЕЗУЛЬТАТЫ:')
    print(f'Средняя ошибка ДО очистки (MSE):    {avg_before:.6f}')
    print(f'Средняя ошибка ПОСЛЕ очистки (MSE): {avg_after:.6f}')
    print(f'Улучшение:                    {improvement:.2f}%')
    print(f'Прирост SNR:                  +{snr_gain:.2f} дБ')


def process_request(audio_bytes: bytes) -> bytes:
    """
    Основная точка входа для Rust-сервера:
    принимает сырые байты WAV, чистит их в памяти и возвращает байты.
    """
    audio = bytes_to_audio(audio_bytes)
    clean_audio = denoise_audio(audio)
    return audio_to_bytes(clean_audio)


if __name__ == '__main__':
    dataset = ComplexAudioDataset(train_clean_dir, train_noisy_dir, max_files=3500)

    if len(dataset) == 0:
        print("Ошибка: датасет пуст или пути указаны неверно.")
        exit()

    dataloader = DataLoader(dataset, batch_size=16, shuffle=True)
    model = ComplexUNetDenoiser().to(device)

    criterion = nn.L1Loss()
    optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=2
    )

    EPOCHS = 30
    print("Старт обучения комплексной U-Net...")
    for epoch in range(EPOCHS):
        model.train()
        running_loss = 0.0
        for inputs, targets in dataloader:
            inputs, targets = inputs.to(device), targets.to(device)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            running_loss += loss.item()
        epoch_loss = running_loss / len(dataloader)
        scheduler.step(epoch_loss)
        current_lr = optimizer.param_groups[0]['lr']
        print(f"Эпоха [{epoch + 1}/{EPOCHS}]    Loss: {epoch_loss :.6f}")

    torch.save(model.state_dict(), model_path)
    print(f"Модель сохранена: {model_path}")



    print("Проверка качества на тестовых файлах...")
    evaluate(model, test_clean_dir, test_noisy_dir)

def main():
    parser = argparse.ArgumentParser(description='Комплексный U-Net Denoiser CLI')
    sub = parser.add_subparsers(dest='command', required=True)

    p_train = sub.add_parser('train', help='Обучить модель')
    p_train.add_argument('--max-files', type=int, default=3500)
    p_train.add_argument('--max-test-files', type=int, default=200)
    p_train.add_argument('--epochs', type=int, default=30)

    p_test = sub.add_parser('test', help='Проверить метрики модели')
    p_test.add_argument('--max-files', type=int, default=200)

    p_denoise = sub.add_parser('denoise', help='Очистить один файл')
    p_denoise.add_argument('input', help='Путь к зашумленному wav')
    p_denoise.add_argument('output', help='Путь для сохранения очищенного wav')

    args = parser.parse_args()

    if args.command == 'train':
        train(max_files=args.max_files, max_test_files=args.max_test_files, epochs=args.epochs)
    elif args.command == 'test':
        model = get_model()
        evaluate(model, test_clean_dir, test_noisy_dir, max_test_files=args.max_files)
    elif args.command == 'denoise':
        clean_audio, _ = denoise_audio(args.input)
        save_wav(clean_audio, args.output)
        print(f"Очищенный файл сохранен в: {args.output}")


if __name__ == '__main__':
    main()