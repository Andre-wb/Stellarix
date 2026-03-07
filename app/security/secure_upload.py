"""
Модуль для безопасной загрузки файлов.

Предоставляет:
- Конфигурацию допустимых типов файлов, размеров, квот.
- Детектор аномалий (двойное расширение, null-байты, path traversal, zip-бомбы).
- Валидацию MIME-типа и содержимого изображений.
- Управление квотами загрузок (для пользователей и IP).
- Сохранение временных файлов с безопасными именами.
- Функции для чтения файла по частям (chunked) с контролем размера.
Vortex/app/security/secure_upload.py
"""

import os
import hashlib
import secrets
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from fastapi import UploadFile, HTTPException, Request
from PIL import Image
import PIL
import io
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)
try:
    import magic as _magic_lib
    _MAGIC_AVAILABLE = True
except (ImportError, OSError):
    _magic_lib = None
    _MAGIC_AVAILABLE = False
    logger.warning(
        "python-magic / libmagic не найдены — MIME-валидация будет по расширению. "
        "Установите: pip install python-magic && apt-get install libmagic1"
    )


class FileUploadConfig:
    """Настройки загрузки файлов."""
    MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024

    # Ограничения для изображений
    MAX_IMAGE_DIMENSION = 10000
    MIN_IMAGE_DIMENSION = 50

    # Допустимые MIME-типы и соответствующие расширения
    ALLOWED_MIME_TYPES: dict[str, list[str]] = {
        # ── Изображения ──────────────────────────────────────────────────
        'image/jpeg':     ['.jpg', '.jpeg', '.jfif', '.jpe'],   # FIX: добавлены .jfif/.jpe (iPhone, Windows)
        'image/png':      ['.png'],
        'image/webp':     ['.webp'],
        'image/gif':      ['.gif'],
        'image/bmp':      ['.bmp'],
        'image/tiff':     ['.tif', '.tiff'],
        'image/svg+xml':  ['.svg'],
        # HEIC/HEIF (iPhone): magic возвращает разные строки в зависимости от libmagic версии
        'image/heic':     ['.heic', '.heif'],
        'image/heif':     ['.heic', '.heif'],
        # ── Видео ────────────────────────────────────────────────────────
        'video/mp4':        ['.mp4', '.m4v'],
        'video/webm':       ['.webm'],
        'video/quicktime':  ['.mov', '.qt'],
        'video/x-msvideo':  ['.avi'],
        'video/x-matroska': ['.mkv'],
        'video/3gpp':       ['.3gp'],
        # ── Аудио ────────────────────────────────────────────────────────
        'audio/mpeg':       ['.mp3'],
        'audio/ogg':        ['.ogg', '.oga'],
        'audio/wav':        ['.wav'],
        'audio/x-wav':      ['.wav'],
        'audio/webm':       ['.weba'],
        'audio/aac':        ['.aac', '.m4a'],
        'audio/flac':       ['.flac'],
        'audio/x-flac':     ['.flac'],
        'audio/mp4':        ['.m4a', '.mp4'],
        # ── Документы ────────────────────────────────────────────────────
        'application/pdf':  ['.pdf'],
        'text/plain':       ['.txt', '.log', '.md', '.csv'],
        'text/csv':         ['.csv'],
        # ── Архивы ───────────────────────────────────────────────────────
        'application/zip':                ['.zip'],
        'application/x-zip-compressed':   ['.zip'],
        'application/x-rar-compressed':   ['.rar'],
        'application/x-7z-compressed':    ['.7z'],
        'application/gzip':               ['.gz'],
        'application/x-tar':              ['.tar'],
    }
    ALLOWED_EXTENSIONS = {ext for exts in ALLOWED_MIME_TYPES.values() for ext in exts}

    # Квоты загрузок
    MAX_FILES_PER_HOUR = 10
    MAX_FILES_PER_DAY = 50
    MAX_MEMORY_BUFFER = 10 * 1024 * 1024 * 1024
    # Время жизни временных файлов в секундах (для очистки)
    TEMP_FILE_LIFETIME = 300

    # Включать ли дополнительные проверки содержимого
    REQUIRE_CONTENT_VALIDATION = True
    CHECK_FOR_MALICIOUS_CONTENT = True


class FileAnomalyDetector:
    """
    Класс для обнаружения подозрительных файлов.
    """

    @staticmethod
    def detect_double_extension(filename: str) -> bool:
        """
        Проверяет наличие двойного расширения с опасным промежуточным расширением.
        Флагирует: shell.php.jpg, virus.exe.png
        НЕ флагирует: photo.vacation.jpg, my.photo.png, photo 2024-01-01 12.34.jpg
        """
        _DANGEROUS_EXTS = frozenset({
            '.php', '.php3', '.php4', '.php5', '.phtml',
            '.asp', '.aspx', '.ascx', '.ashx',
            '.jsp', '.jspx', '.jws',
            '.cgi', '.pl', '.py', '.rb', '.sh', '.bash',
            '.exe', '.dll', '.bat', '.cmd', '.ps1', '.vbs',
        })
        name  = Path(filename).name
        parts = name.split('.')
        if len(parts) <= 2:
            return False
        # Только промежуточные части (исключаем первую часть и последнее расширение)
        intermediate = {'.' + p.lower() for p in parts[1:-1]}
        return bool(intermediate & _DANGEROUS_EXTS)

    @staticmethod
    def detect_null_bytes(filename: str) -> bool:
        """Проверяет наличие null-байтов в имени файла."""
        return '\x00' in filename

    @staticmethod
    def detect_path_traversal(filename: str) -> bool:
        """
        Проверяет наличие признаков path traversal или инъекций.
        """
        dangerous_patterns = [
            '..', '/', '\\', '~',
            'C:', 'D:',
            '/etc/', '/bin/', '/usr/bin/',
            '<?php', '<script', 'javascript:'
        ]
        return any(pattern in filename for pattern in dangerous_patterns)

    @staticmethod
    async def validate_image_content(content: bytes) -> Tuple[bool, Optional[str]]:
        """
        Проверяет, что содержимое является корректным изображением,
        не превышает допустимые размеры и имеет нормальное соотношение сторон.
        """
        try:
            if len(content) < 12:
                return False, "Файл слишком мал для проверки"

            img = Image.open(io.BytesIO(content))

            # Конвертируем в RGB, если нужно (удаляем альфа-канал и т.п.)
            if hasattr(img, 'mode'):
                if img.mode in ['RGBA', 'CMYK', 'YCbCr', 'LAB', 'HSV']:
                    img = img.convert('RGB')

            width, height = img.size
            if width > FileUploadConfig.MAX_IMAGE_DIMENSION or height > FileUploadConfig.MAX_IMAGE_DIMENSION:
                return False, f"Размер изображения слишком большой: {width}x{height}"

            if width < FileUploadConfig.MIN_IMAGE_DIMENSION or height < FileUploadConfig.MIN_IMAGE_DIMENSION:
                return False, f"Размер изображения слишком маленький: {width}x{height}"

            aspect_ratio = width / height if height > 0 else 0
            if aspect_ratio > 10 or aspect_ratio < 0.1:
                return False, f"Некорректное соотношение сторон: {aspect_ratio:.2f}"

            img.close()
            return True, None

        except PIL.UnidentifiedImageError:
            return False, "Невозможно идентифицировать изображение"
        except Exception as e:
            logger.warning(f"Ошибка валидации изображения: {str(e)}")
            return False, f"Ошибка обработки изображения: {str(e)[:100]}"

    @staticmethod
    def calculate_file_complexity(content: bytes) -> float:
        """
        Вычисляет энтропию содержимого файла.
        Высокая энтропия может указывать на сжатые или зашифрованные данные (zip-бомбы).
        """
        if len(content) == 0:
            return 0

        freq = {}
        for byte in content:
            freq[byte] = freq.get(byte, 0) + 1

        entropy = 0
        total = len(content)
        for count in freq.values():
            probability = count / total
            if probability > 0:
                entropy -= probability * (probability.bit_length())  # приближённо log2

        return entropy

    @staticmethod
    def detect_zip_bomb_indicators(content: bytes) -> bool:
        """
        Проверяет, не является ли файл zip-бомбой (очень маленький архив с огромной энтропией).
        """
        if len(content) < 1000:
            return False

        archive_magic_numbers = [
            b'PK\x03\x04',      # ZIP
            b'PK\x05\x06',      # ZIP (central directory)
            b'PK\x07\x08',      # ZIP (spanned)
            b'\x1f\x8b',        # GZIP
            b'BZh',             # BZIP2
            b'\x50\x4b',        # ZIP (альтернатива)
        ]

        for magic_num in archive_magic_numbers:
            if content.startswith(magic_num):
                entropy = FileAnomalyDetector.calculate_file_complexity(content)
                if entropy > 7.5:   # Эмпирическое значение
                    return True

        return False


class UploadQuotaManager:
    """
    Менеджер квот загрузок, использующий БД для учёта количества файлов от пользователя и IP.
    """

    def __init__(self, db: Session):
        self.db = db

    async def check_user_quota(self, user_id: Optional[int], client_ip: str) -> Tuple[bool, Optional[str]]:
        """
        Проверяет, не превысил ли пользователь или IP лимиты загрузок.
        Возвращает (True, None) если лимиты не превышены, иначе (False, сообщение).
        """
        try:
            # Импортируем модель внутри функции, чтобы избежать циклических импортов
            from app.models import UploadQuota

            current_time = datetime.utcnow()
            hour_ago = current_time - timedelta(hours=1)
            day_ago = current_time - timedelta(days=1)

            if user_id:
                # Часовая квота для пользователя
                hour_count = self.db.query(func.count(UploadQuota.id)).filter(
                    UploadQuota.user_id == user_id,
                    UploadQuota.uploaded_at >= hour_ago
                ).scalar() or 0

                if hour_count >= FileUploadConfig.MAX_FILES_PER_HOUR:
                    return False, "Превышена часовая квота загрузок"

                # Дневная квота для пользователя
                day_count = self.db.query(func.count(UploadQuota.id)).filter(
                    UploadQuota.user_id == user_id,
                    UploadQuota.uploaded_at >= day_ago
                ).scalar() or 0

                if day_count >= FileUploadConfig.MAX_FILES_PER_DAY:
                    return False, "Превышена дневная квота загрузок"

            # Проверка квоты по IP (более строгая: в два раза больше лимита пользователя)
            ip_hour_count = self.db.query(func.count(UploadQuota.id)).filter(
                UploadQuota.client_ip == client_ip,
                UploadQuota.uploaded_at >= hour_ago
            ).scalar() or 0

            if ip_hour_count >= FileUploadConfig.MAX_FILES_PER_HOUR * 2:
                return False, "Превышен лимит загрузок с вашего IP"

            return True, None
        except Exception as e:
            logger.error(f"Ошибка проверки квот: {e}")
            return False, "Ошибка проверки квот"

    async def record_upload(self, user_id: Optional[int], client_ip: str, file_size: int, file_hash: Optional[str] = None):
        """
        Записывает факт загрузки в БД для учёта квот.
        """
        try:
            from app.models import UploadQuota

            upload_record = UploadQuota(
                user_id=user_id,
                client_ip=client_ip,
                file_size=file_size,
                file_hash=file_hash,
                uploaded_at=datetime.utcnow()
            )
            self.db.add(upload_record)
            self.db.commit()
        except Exception as e:
            logger.error(f"Ошибка записи квоты: {e}")
            self.db.rollback()


def generate_secure_filename(extension: str) -> str:
    """
    Генерирует безопасное имя файла: случайная строка + расширение.
    Используется secrets.token_urlsafe для криптостойкости.
    """
    return secrets.token_urlsafe(16) + extension


def calculate_file_hash(content: bytes) -> str:
    """Возвращает SHA256 хеш содержимого файла."""
    return hashlib.sha256(content).hexdigest()


def validate_file_mime_type(content: bytes, filename: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет MIME-тип файла по первым байтам и соответствие расширения.
    Возвращает (успех, MIME-тип или сообщение об ошибке).
    """
    file_ext = Path(filename).suffix.lower()

    # ── Шаг 1: определяем MIME по magic bytes (если libmagic доступна) ───────
    if _MAGIC_AVAILABLE and _magic_lib is not None:
        try:
            mime = _magic_lib.from_buffer(content[:4096], mime=True)
        except Exception as e:
            logger.warning(f"libmagic ошибка: {e} — переходим к fallback по расширению")
            mime = None
    else:
        mime = None

    # ── Шаг 2: если magic не дала результат — определяем по расширению ───────
    if mime is None:
        # Fallback: ищем MIME по расширению файла
        ext_to_mime = {
            ext: mime_type
            for mime_type, exts in FileUploadConfig.ALLOWED_MIME_TYPES.items()
            for ext in exts
        }
        mime = ext_to_mime.get(file_ext)
        if mime is None:
            return False, f"Неподдерживаемое расширение файла: {file_ext}"

    # ── Шаг 3: проверяем что MIME входит в белый список ─────────────────────
    if mime not in FileUploadConfig.ALLOWED_MIME_TYPES:
        # Попытка нормализации: некоторые libmagic версии возвращают x-субтипы
        # например 'audio/x-wav' вместо 'audio/wav' или 'image/x-png' вместо 'image/png'
        normalized = mime.replace('/x-', '/', 1)
        if normalized in FileUploadConfig.ALLOWED_MIME_TYPES:
            mime = normalized
        else:
            return False, f"Неподдерживаемый тип файла: {mime}"

    # ── Шаг 4: проверяем расширение — мягкая проверка ───────────────────────
    expected_exts = FileUploadConfig.ALLOWED_MIME_TYPES.get(mime, [])
    if file_ext and expected_exts and file_ext not in expected_exts:
        mime_category = mime.split('/')[0]
        # Находим все расширения для данной категории
        all_category_exts: set[str] = set()
        for m, exts in FileUploadConfig.ALLOWED_MIME_TYPES.items():
            if m.startswith(mime_category + '/'):
                all_category_exts.update(exts)
        if file_ext not in all_category_exts:
            return False, (
                f"Расширение «{file_ext}» не соответствует типу файла «{mime}». "
                f"Ожидаются: {', '.join(expected_exts)}"
            )

    return True, mime


def save_temp_file(content: bytes, extension: str) -> Tuple[Path, Path]:
    """
    Сохраняет содержимое во временный файл с безопасным именем.
    Возвращает кортеж (путь к временной директории, путь к файлу).
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="secure_upload_"))
    safe_filename = generate_secure_filename(extension)
    temp_file_path = temp_dir / safe_filename

    try:
        with open(temp_file_path, 'wb') as f:
            f.write(content)

        # Устанавливаем права только для владельца
        os.chmod(temp_file_path, 0o600)
        return temp_dir, temp_file_path
    except Exception as e:
        logger.error(f"Ошибка сохранения временного файла: {e}")
        raise


def cleanup_temp_files(temp_dir: Path, temp_file_path: Path):
    """
    Удаляет временный файл и, если директория пуста, удаляет её.
    """
    try:
        if temp_file_path.exists() and temp_file_path.parent == temp_dir:
            os.remove(temp_file_path)
        if temp_dir.exists():
            if not any(temp_dir.iterdir()):
                os.rmdir(temp_dir)
    except Exception as e:
        logger.warning(f"Ошибка при очистке временных файлов: {str(e)}")


async def read_file_chunked(file: UploadFile, max_size: int = FileUploadConfig.MAX_FILE_SIZE) -> Tuple[bytes, int]:
    """
    Читает файл по частям (chunked), контролируя общий размер.
    Возвращает кортеж (содержимое, размер в байтах).
    При превышении max_size выбрасывает HTTPException с кодом 413.
    """
    file_content = bytearray()
    total_size = 0

    while True:
        chunk = await file.read(8192)  # читаем по 8 KB
        if not chunk:
            break

        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой. Максимальный размер: {max_size // 1024 // 1024}MB"
            )

        file_content.extend(chunk)

    return bytes(file_content), total_size