from __future__ import annotations
import os, secrets
from pathlib import Path

_ENV = Path(".env")


def _read_env() -> None:
    if _ENV.exists():
        for line in _ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_read_env()


def _auto_secret(key: str) -> str:
    val = os.getenv(key)
    if not val:
        val = secrets.token_hex(32)
        with open(_ENV, "a") as f:
            f.write(f"\n{key}={val}\n")
        os.environ[key] = val
    return val


class Config:
    JWT_SECRET = _auto_secret("JWT_SECRET")
    CSRF_SECRET = _auto_secret("CSRF_SECRET")
    ACCESS_TOKEN_EXPIRE_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MIN", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "9000"))
    DEVICE_NAME = os.getenv("DEVICE_NAME", "")
    DB_PATH = os.getenv("DB_PATH", "vortex.db")
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
    KEYS_DIR = Path(os.getenv("KEYS_DIR", "keys"))
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    IS_PRODUCTION = ENVIRONMENT == "production"
    UDP_PORT = int(os.getenv("UDP_PORT", "4200"))
    UDP_INTERVAL_SEC = int(os.getenv("UDP_INTERVAL_SEC", "2"))
    PEER_TIMEOUT_SEC = int(os.getenv("PEER_TIMEOUT_SEC", "15"))
    MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "100"))
    MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
    WAF_RATE_LIMIT_REQUESTS = int(os.getenv("WAF_RATE_LIMIT_REQUESTS", "120"))
    WAF_RATE_LIMIT_WINDOW = int(os.getenv("WAF_RATE_LIMIT_WINDOW", "60"))
    WAF_BLOCK_DURATION = int(os.getenv("WAF_BLOCK_DURATION", "3600"))

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.KEYS_DIR.mkdir(parents=True, exist_ok=True)