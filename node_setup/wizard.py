# node_setup/wizard.py
# ==============================================================================
# Модуль мастера настройки узла Vortex.
# Запускает временный веб-сервер (FastAPI) для проведения начальной конфигурации:
#   - проверка системной информации
#   - валидация портов
#   - создание SSL-сертификатов (самоподписанные, mkcert, Let's Encrypt, ручные)
#   - сохранение параметров в .env
#   - завершение мастера и запуск основного приложения
# ==============================================================================

from __future__ import annotations
import json
import logging
import os
import platform
import secrets
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .models import SelfSignedRequest, ManualCertRequest, LetsEncryptRequest, NodeConfig
from node_setup.ssl_manager import (
    SSLResult,
    check_cert_expiry,
    detect_available_methods,
    generate_letsencrypt,
    generate_self_signed,
    generate_with_mkcert,
    get_ca_install_instructions,
    use_manual_cert,
)

logger = logging.getLogger(__name__)

# Файл с переменными окружения, который будет создан/дополнен
ENV_FILE = Path(".env")
# Директория для хранения сертификатов
CERT_DIR = Path("certs")

# FastAPI-приложение мастера (без документации, т.к. это внутренний интерфейс)
wizard_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Подключаем статические файлы (CSS, JS для веб-интерфейса)
_STATIC_DIR = Path(__file__).parent / "static"
wizard_app.mount("/setup", StaticFiles(directory=str(_STATIC_DIR)), name="setup_static")

# Глобальная переменная для управления сервером
_server_instance: uvicorn.Server | None = None
# Событие, сигнализирующее о завершении настройки (остановка сервера)
_setup_done = threading.Event()


def _load_html() -> str:
    """Загружает HTML-шаблон страницы мастера."""
    html_path = Path(__file__).parent / "templates" / "setup.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>setup.html не найден</h1>"


@wizard_app.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница мастера (отдаёт HTML)."""
    return _load_html()


@wizard_app.get("/api/info")
async def system_info():
    """
    Возвращает системную информацию для отображения в интерфейсе:
    - hostname
    - ОС
    - локальные IP-адреса (определяются через сокет)
    - доступные методы генерации SSL
    - наличие существующих сертификатов
    - признак инициализации узла (NODE_INITIALIZED в .env)
    """
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Пытаемся подключиться к разным адресам, чтобы узнать реальный IP
        for t in ("192.168.1.1", "10.0.0.1", "8.8.8.8"):
            try:
                s.connect((t, 80))
                ip = s.getsockname()[0]
                if not ip.startswith("127."):
                    ips.append(ip)
                    break
            except Exception:
                pass
        s.close()
    except Exception:
        pass

    return {
        "hostname":   socket.gethostname(),
        "platform":   platform.system(),
        "local_ips":  ips,
        "ssl_methods": detect_available_methods(),
        "cert_exists": (CERT_DIR / "vortex.crt").exists(),
        "initialized": _read_env_dict().get("NODE_INITIALIZED") == "true",
    }


@wizard_app.get("/api/validate/port/{port}")
async def validate_port(port: int):
    """
    Проверяет, свободен ли указанный порт (попытка привязаться к 127.0.0.1).
    Возвращает ok: True/False и сообщение.
    """
    if not (1024 <= port <= 65535):
        return {"ok": False, "message": "Порт должен быть от 1024 до 65535"}
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return {"ok": True, "message": f"Порт {port} свободен"}
    except OSError:
        return {"ok": False, "message": f"Порт {port} уже занят"}


@wizard_app.post("/api/ssl/self-signed")
async def ssl_self_signed(body: SelfSignedRequest):
    """
    Генерирует самоподписанный сертификат с помощью ssl_manager.
    Возвращает пути к файлам и инструкцию по установке CA.
    """
    result = generate_self_signed(
        cert_dir    = CERT_DIR,
        hostname    = body.hostname or socket.gethostname(),
        org_name    = body.org_name,
        install_ca  = body.install_ca,
    )
    if not result.ok:
        raise HTTPException(500, result.message)

    ca_cmd = ""
    if not result.trusted and result.ca:
        ca_cmd = get_ca_install_instructions(Path(result.ca))

    return {
        "ok":          True,
        "cert":        result.cert,
        "key":         result.key,
        "ca":          result.ca,
        "trusted":     result.trusted,
        "message":     result.message,
        "ca_install":  ca_cmd,
    }


@wizard_app.post("/api/ssl/letsencrypt")
async def ssl_letsencrypt(body: LetsEncryptRequest):
    """
    Запрашивает сертификат Let's Encrypt через certbot.
    Требует указания домена и email.
    """
    if not body.domain:
        raise HTTPException(400, "Укажите домен")
    result = generate_letsencrypt(
        cert_dir = CERT_DIR,
        domain   = body.domain,
        email    = body.email,
        staging  = body.staging,
    )
    if not result.ok:
        raise HTTPException(500, result.message)
    return {"ok": True, "cert": result.cert, "key": result.key, "message": result.message}


@wizard_app.post("/api/ssl/mkcert")
async def ssl_mkcert():
    """
    Генерирует сертификат через mkcert (локально доверенный).
    """
    result = generate_with_mkcert(CERT_DIR)
    if not result.ok:
        raise HTTPException(500, result.message)
    return {"ok": True, "cert": result.cert, "key": result.key,
            "trusted": result.trusted, "message": result.message}


@wizard_app.post("/api/ssl/manual")
async def ssl_manual(body: ManualCertRequest):
    """
    Принимает пути к существующим сертификатам (пользователь загрузил свои).
    Копирует их в рабочую директорию.
    """
    if not Path(body.cert_path).exists():
        raise HTTPException(400, f"Файл не найден: {body.cert_path}")
    if not Path(body.key_path).exists():
        raise HTTPException(400, f"Файл не найден: {body.key_path}")
    result = use_manual_cert(body.cert_path, body.key_path, CERT_DIR)
    if not result.ok:
        raise HTTPException(500, result.message)
    return {"ok": True, "message": result.message}


@wizard_app.get("/api/ssl/status")
async def ssl_status():
    """
    Проверяет наличие сертификата и его срок действия.
    Возвращает информацию для отображения в интерфейсе.
    """
    cert_path = CERT_DIR / "vortex.crt"
    if not cert_path.exists():
        return {"exists": False}
    info = check_cert_expiry(cert_path)
    return {"exists": True, **info}


@wizard_app.get("/api/ssl/skip")
async def ssl_skip():
    """Пропустить SSL — запускать по HTTP."""
    return {"ok": True, "message": "SSL пропущен, узел будет работать по HTTP"}


@wizard_app.post("/api/config/save")
async def save_config(body: NodeConfig):
    """
    Сохраняет основную конфигурацию узла в .env файл.
    Генерирует секреты JWT и CSRF, если их ещё нет.
    """
    if not body.device_name.strip():
        raise HTTPException(400, "Укажите имя устройства")
    if not (1024 <= body.port <= 65535):
        raise HTTPException(400, "Неверный порт")

    _write_env(body)
    return {"ok": True, "message": "Конфигурация сохранена"}


@wizard_app.post("/api/setup/complete")
async def complete_setup():
    """
    Завершает настройку:
    - Добавляет NODE_INITIALIZED=true в .env
    - Запускает фоновый поток для остановки сервера мастера
    - Возвращает URL, по которому будет доступен основной узел
    """
    env = _read_env_dict()
    lines = Path(".env").read_text(encoding="utf-8") if Path(".env").exists() else ""

    if "NODE_INITIALIZED=true" not in lines:
        with open(".env", "a", encoding="utf-8") as f:
            f.write("\nNODE_INITIALIZED=true\n")
    threading.Thread(target=_shutdown_wizard, daemon=True).start()

    port = int(env.get("PORT", "8000"))
    ssl = (CERT_DIR / "vortex.crt").exists()
    proto = "https" if ssl else "http"

    return {
        "ok": True,
        "message": "Настройка завершена! Запускаем узел...",
        "url": f"{proto}://localhost:{port}",
    }


def _shutdown_wizard():
    """Функция, вызываемая после завершения настройки: через 1.5 сек останавливает сервер."""
    time.sleep(1.5)
    _setup_done.set()
    if _server_instance:
        _server_instance.should_exit = True


def _read_env_dict() -> dict[str, str]:
    """Читает текущий .env файл и возвращает словарь переменных."""
    if not ENV_FILE.exists():
        return {}
    result = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(cfg: NodeConfig) -> None:
    """
    Записывает (или перезаписывает) .env файл с параметрами узла.
    Генерирует новые секреты, если их нет в существующем файле.
    """
    existing = _read_env_dict()

    jwt_secret  = existing.get("JWT_SECRET")  or secrets.token_hex(32)
    csrf_secret = existing.get("CSRF_SECRET") or secrets.token_hex(32)

    lines = [
        "# ⚡ VORTEX Node Configuration",
        f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "# Security (DO NOT SHARE)",
        f"JWT_SECRET={jwt_secret}",
        f"CSRF_SECRET={csrf_secret}",
        "",
        "# Tokens",
        f"ACCESS_TOKEN_EXPIRE_MIN=1440",
        f"REFRESH_TOKEN_EXPIRE_DAYS=30",
        "",
        "# Server",
        f"HOST={cfg.host}",
        f"PORT={cfg.port}",
        f"DEVICE_NAME={cfg.device_name}",
        f"ENVIRONMENT={cfg.environment}",
        "",
        "# Storage",
        f"DB_PATH=vortex.db",
        f"UPLOAD_DIR=uploads",
        f"KEYS_DIR=keys",
        f"MAX_FILE_MB={cfg.max_file_mb}",
        "",
        "# P2P Discovery",
        f"UDP_PORT={cfg.udp_port}",
        f"UDP_INTERVAL_SEC=2",
        f"PEER_TIMEOUT_SEC=15",
        "",
        "# WAF",
        f"WAF_RATE_LIMIT_REQUESTS=120",
        f"WAF_RATE_LIMIT_WINDOW=60",
        f"WAF_BLOCK_DURATION=3600",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_wizard(host: str = "127.0.0.1", port: int = 7979) -> None:
    """
    Запускает сервер мастера на указанном хосте и порту.
    Функция блокируется до тех пор, пока не будет вызвано _setup_done.
    """
    global _server_instance

    config = uvicorn.Config(
        app      = wizard_app,
        host     = host,
        port     = port,
        log_level= "warning",
        access_log = False,
    )
    _server_instance = uvicorn.Server(config)

    thread = threading.Thread(target=_server_instance.run, daemon=True)
    thread.start()

    try:
        _setup_done.wait()  # ждём сигнала завершения
    except KeyboardInterrupt:
        pass
    finally:
        if _server_instance:
            _server_instance.should_exit = True
        thread.join(timeout=3)