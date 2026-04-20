"""
⚡ VORTEX Node Launcher
────────────────────────
Единственная точка входа для узла.

  python run.py              — запустить (wizard при первом запуске, иначе узел)
  python run.py --setup      — принудительно открыть мастер настройки
  python run.py --status     — показать статус узла
  python run.py --reset      — сбросить настройки (требует подтверждения)
  python run.py --wizard-port 9090   — указать порт wizard-а (по умолчанию 7979)
  python run.py --no-browser — не открывать браузер автоматически
"""
from __future__ import annotations

import argparse
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
import shutil
from typing import NamedTuple


# ── Константы ─────────────────────────────────────────────────────────────────

ENV_FILE  = Path(".env")
CERT_DIR  = Path("certs")
CERT_FILE = CERT_DIR / "vortex.crt"
KEY_FILE  = CERT_DIR / "vortex.key"

class SSLResult(NamedTuple):
    ok: bool
    cert: str
    key: str
    ca: str
    message: str
    trusted: bool

BANNER = r"""
  ██╗   ██╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗
  ██║   ██║██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝
  ██║   ██║██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝
  ╚██╗ ██╔╝██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗
   ╚████╔╝ ╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗
    ╚═══╝   ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
"""


# ── Вывод в терминал ──────────────────────────────────────────────────────────

def _p(text: str, color: str = "") -> None:
    _colors = {
        "green":  "\033[92m",
        "red":    "\033[91m",
        "yellow": "\033[93m",
        "cyan":   "\033[96m",
        "dim":    "\033[2m",
    }
    reset = "\033[0m" if color else ""
    print(f"{_colors.get(color, '')}{text}{reset}", flush=True)


# ── .env ──────────────────────────────────────────────────────────────────────

def _read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    result = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _is_initialized() -> bool:
    return _read_env().get("NODE_INITIALIZED") == "true"


# ── Сеть ─────────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Определяет локальный IP без необходимости в интернете."""
    for target in ("192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except Exception:
            pass
    return "127.0.0.1"


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Ждёт пока порт не начнёт принимать соединения."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.15)
    return False


# ── Браузер ───────────────────────────────────────────────────────────────────

def _open_browser(url: str) -> None:
    """
    Открывает браузер надёжно на macOS, Windows и Linux.

    Три ключевых исправления по сравнению с webbrowser.open():
      1. daemon=False — поток не убивается до срабатывания (критично на macOS)
      2. subprocess(['open', url]) на macOS — надёжнее webbrowser
      3. Вызывается только ПОСЛЕ _wait_for_port() — сервер уже готов
    """
    def _do() -> None:
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(
                    ["open", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif system == "Windows":
                subprocess.Popen(
                    ["cmd", "/c", "start", "", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                try:
                    subprocess.Popen(
                        ["xdg-open", url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except FileNotFoundError:
                    webbrowser.open(url)
        except Exception:
            try:
                webbrowser.open(url)
            except Exception:
                pass

    threading.Thread(target=_do, daemon=False).start()


# ── Проверки ──────────────────────────────────────────────────────────────────

def _check_python() -> None:
    if sys.version_info < (3, 10):
        _p(f"✗ Требуется Python 3.10+. Установлен: {platform.python_version()}", "red")
        sys.exit(1)


def _check_deps() -> list[str]:
    missing = []
    for pkg in ["fastapi", "uvicorn", "cryptography", "sqlalchemy", "jwt"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


# ── --status ──────────────────────────────────────────────────────────────────

def cmd_status() -> None:
    _p(BANNER, "cyan")
    env  = _read_env()
    done = env.get("NODE_INITIALIZED") == "true"
    ssl  = CERT_FILE.exists() and KEY_FILE.exists()
    ip   = _local_ip()

    _p("─" * 54, "dim")
    _p(f"  Статус:          {'✓ Настроен' if done else '✗ Не настроен'}",
       "green" if done else "red")
    if done:
        port  = env.get("PORT", "9000")
        proto = "https" if ssl else "http"
        _p(f"  Имя устройства:  {env.get('DEVICE_NAME', 'не задано')}")
        _p(f"  Адрес:           {proto}://localhost:{port}", "cyan")
        if ip != "127.0.0.1":
            _p(f"  В сети:          {proto}://{ip}:{port}  ← другие устройства", "cyan")
        _p(f"  SSL:             {'✓ ' + str(CERT_FILE) if ssl else '✗ нет'}",
           "green" if ssl else "yellow")
        _p(f"  База данных:     {env.get('DB_PATH', 'vortex.db')}")
    _p("─" * 54, "dim")


# ── --reset ───────────────────────────────────────────────────────────────────

def cmd_reset() -> None:
    _p("\n⚠  Это сбросит все настройки узла!", "yellow")
    _p("   База данных и загруженные файлы останутся нетронутыми.", "dim")
    confirm = input("\n   Введите 'RESET' для подтверждения: ").strip()
    if confirm != "RESET":
        _p("   Отменено.", "dim")
        return
    deleted = []
    if ENV_FILE.exists():
        ENV_FILE.unlink()
        deleted.append(".env")
    if CERT_DIR.exists():
        shutil.rmtree(CERT_DIR)
        deleted.append("certs/")
    _p(f"\n✓ Удалено: {', '.join(deleted) if deleted else 'нечего удалять'}", "green")
    _p("  Запустите 'python run.py' для повторной настройки.\n", "cyan")


# ── --generate-worker ─────────────────────────────────────────────────────────

def cmd_generate_worker(backend_url: str) -> None:
    """Генерация файлов Cloudflare Worker для CDN relay."""
    import secrets

    if not backend_url:
        env = _read_env()
        port = env.get("PORT", "9000")
        _p("⚠  Не указан --backend. Укажите URL вашего Vortex-сервера:", "yellow")
        _p(f"   python run.py --generate-worker --backend https://your-server.com:{port}", "cyan")
        sys.exit(1)

    relay_secret = secrets.token_hex(32)

    from app.transport.cdn_relay import generate_worker_files
    output_dir = generate_worker_files(backend_url, relay_secret)

    _p(f"\n✓ Cloudflare Worker сгенерирован в {output_dir}/", "green")
    _p(f"  Секрет:  {relay_secret}", "cyan")
    _p(f"  Бэкенд: {backend_url}", "cyan")
    _p("\n  Следующие шаги:", "dim")
    _p("  1. npm install -g wrangler", "dim")
    _p("  2. wrangler login", "dim")
    _p(f"  3. cd {output_dir} && wrangler deploy", "dim")
    _p("\n  Добавьте в .env на клиенте:", "yellow")
    _p(f"  CDN_RELAY_URL=https://vortex-relay.<username>.workers.dev", "cyan")
    _p(f"  CDN_RELAY_SECRET={relay_secret}\n", "cyan")


# ── Первый запуск (интерактивный) ─────────────────────────────────────────────

def cmd_first_launch() -> None:
    """Интерактивная настройка при первом запуске — прямо в консоли."""
    _p(BANNER, "cyan")
    _p("  ⚡ Первый запуск — настройка узла\n", "cyan")

    # ── 1. Имя устройства ────────────────────────────────────────────────
    default_name = platform.node()
    name = input(f"  Имя устройства [{default_name}]: ").strip() or default_name

    # ── 2. Порт ──────────────────────────────────────────────────────────
    port = input("  Порт [9000]: ").strip() or "9000"

    # ── 3. Режим сети ────────────────────────────────────────────────────
    _p("\n  Режим сети:", "cyan")
    _p("    1) 📡 Локальный — Wi-Fi / LAN (без интернета)")
    _p("    2) 🌍 Глобальный — через интернет (Cloudflare Tunnel + обфускация)\n")

    mode_choice = input("  Выберите (1/2) [1]: ").strip()
    network_mode = "global" if mode_choice == "2" else "local"

    # ── 4. Для глобального — проверяем cloudflared ───────────────────────
    if network_mode == "global":
        if not _has_cloudflared():
            _p("\n  ⚠ cloudflared не установлен!", "yellow")
            _p("  Установите: brew install cloudflared  (macOS)", "dim")
            _p("              sudo apt install cloudflared  (Linux)", "dim")
            _p("              Или: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/\n", "dim")

            cont = input("  Продолжить без Cloudflare Tunnel? (y/n) [y]: ").strip().lower()
            if cont == "n":
                _p("  Установите cloudflared и запустите python run.py снова.", "dim")
                sys.exit(0)
        else:
            _p("  ✓ cloudflared найден — туннель запустится автоматически", "green")

    # ── 5. SSL ───────────────────────────────────────────────────────────
    ssl_generated = False
    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        _p("\n  SSL сертификат:", "cyan")
        _p("    1) Сгенерировать самоподписанный (быстро, браузер покажет предупреждение)")
        _p("    2) Пропустить (без HTTPS — звонки не будут работать)\n")

        ssl_choice = input("  Выберите (1/2) [1]: ").strip()
        if ssl_choice != "2":
            try:
                _generate_self_signed_cert()
                ssl_generated = True
                _p("  ✓ SSL сертификат создан", "green")
            except Exception as e:
                _p(f"  ⚠ Ошибка генерации SSL: {e}", "yellow")
    else:
        _p("\n  ✓ SSL сертификат уже существует", "green")

    # ── 6. Регистрация (инвайт) ──────────────────────────────────────────
    _p("\n  Режим регистрации:", "cyan")
    _p("    1) Открытая — все могут зарегистрироваться")
    _p("    2) По инвайт-коду — только по вашему приглашению")
    _p("    3) Закрытая — регистрация отключена\n")

    reg_choice = input("  Выберите (1/2/3) [1]: ").strip()
    reg_mode = "invite" if reg_choice == "2" else ("closed" if reg_choice == "3" else "open")

    invite_code = ""
    if reg_mode == "invite":
        invite_code = secrets.token_hex(8).upper()
        _p(f"\n  ╔══════════════════════════════════╗", "green")
        _p(f"  ║  Инвайт-код: {invite_code:<18s} ║", "cyan")
        _p(f"  ╚══════════════════════════════════╝", "green")
        _p(f"  Отправьте этот код тем кому разрешаете регистрацию.", "dim")

    # ── 7. Записываем .env ───────────────────────────────────────────────
    env_lines = [
        f"DEVICE_NAME={name}",
        f"PORT={port}",
        f"HOST=0.0.0.0",
        f"NETWORK_MODE={network_mode}",
        f"REGISTRATION_MODE={reg_mode}",
        f"NODE_INITIALIZED=true",
    ]
    if invite_code:
        env_lines.append(f"INVITE_CODE_NODE={invite_code}")
    if network_mode == "global":
        env_lines.append("OBFUSCATION_ENABLED=true")
    env_lines.append("STEALTH_MODE=true")

    # Дописываем к существующему .env (секреты уже там)
    with open(ENV_FILE, "a") as f:
        f.write("\n" + "\n".join(env_lines) + "\n")

    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass

    _p(f"\n  ✓ Настройка завершена!", "green")
    _p(f"  Запускаем узел...\n", "cyan")
    time.sleep(1)


def _generate_self_signed_cert() -> None:
    """Генерирует самоподписанный SSL сертификат."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    import ipaddress as _ipa

    CERT_DIR.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    ip = _local_ip()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Vortex Node"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vortex"),
    ])

    san_list = [
        x509.DNSName("localhost"),
        x509.IPAddress(_ipa.IPv4Address("127.0.0.1")),
    ]
    if ip != "127.0.0.1":
        try:
            san_list.append(x509.IPAddress(_ipa.IPv4Address(ip)))
        except ValueError:
            pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_dt.now(_tz.utc))
        .not_valid_after(_dt.now(_tz.utc) + _td(days=365))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_FILE.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(KEY_FILE, 0o600)


# ── Мастер настройки (legacy) ────────────────────────────────────────────────

def cmd_setup(wizard_port: int, no_browser: bool) -> None:
    _p(BANNER, "cyan")
    _p("  ⚡ Открываем мастер настройки узла...\n", "cyan")
    missing = _check_deps()

    if missing:
        _p(f"✗ Отсутствуют зависимости: {', '.join(missing)}", "red")
        _p(f"  Выполните: pip install {' '.join(missing)}", "yellow")
        sys.exit(1)

    try:
        from node_setup.wizard import run_wizard
    except ImportError as e:
        _p(f"✗ Ошибка импорта node_setup: {e}", "red")
        _p("  Убедитесь что папка node_setup/ находится рядом с run.py", "yellow")
        sys.exit(1)

    ip        = _local_ip()
    local_url = f"http://127.0.0.1:{wizard_port}"
    net_url   = f"http://{ip}:{wizard_port}"

    # Запускаем wizard в потоке (daemon=False — не убьётся раньше времени)
    wizard_thread = threading.Thread(
        target=run_wizard,
        kwargs={"host": "0.0.0.0", "port": wizard_port},
        daemon=False,
    )
    wizard_thread.start()

    # Ждём пока сервер реально поднимется — не просто sleep()
    _p("  ⏳ Запуск wizard-а...", "dim")
    if not _wait_for_port(wizard_port, timeout=10.0):
        _p("✗ Wizard не запустился за 10 секунд. Возможно порт занят.", "red")
        sys.exit(1)

    _p(f"\n  🌐 Мастер настройки:")
    _p(f"     Локально:  {local_url}", "cyan")
    if ip != "127.0.0.1":
        _p(f"     В сети:    {net_url}  ← для телефонов и других устройств", "cyan")
    _p("  📌 Нажмите Ctrl+C чтобы выйти\n", "dim")

    # Открываем браузер ТОЛЬКО после того как сервер готов
    if not no_browser:
        _open_browser(local_url)

    try:
        wizard_thread.join()
    except KeyboardInterrupt:
        _p("\n\n  Настройка прервана.", "yellow")
        sys.exit(0)


# ── Cloudflare Tunnel ─────────────────────────────────────────────────────────

def _find_cloudflared() -> str | None:
    """Возвращает абсолютный путь до cloudflared или None.

    Когда run.py запускается из PyInstaller-бандла (двойной клик по .app
    на macOS), PATH урезан и не содержит /opt/homebrew/bin. Проверяем
    все популярные места установки прямо.
    """
    hit = shutil.which("cloudflared")
    if hit:
        return hit
    for c in (
        "/opt/homebrew/bin/cloudflared",
        "/usr/local/bin/cloudflared",
        "/opt/local/bin/cloudflared",
        "/snap/bin/cloudflared",
        "/usr/bin/cloudflared",
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ):
        try:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        except OSError:
            continue
    return None


def _has_cloudflared() -> bool:
    """True если cloudflared установлен где-либо в стандартных путях."""
    return _find_cloudflared() is not None


_tunnel_ready = threading.Event()

def _start_cloudflare_tunnel(port: int, proto: str) -> subprocess.Popen | None:
    """
    Запускает Cloudflare Tunnel в фоне.
    Возвращает процесс или None если cloudflared не установлен.
    """
    if not _has_cloudflared():
        return None

    env = _read_env()
    mode = env.get("NETWORK_MODE", "local")

    # В локальном режиме туннель не нужен
    if mode != "global":
        return None

    _p("  🌐 Запуск Cloudflare Tunnel...", "cyan")

    def _run_tunnel_with_reconnect():
        """Запускает cloudflared с автоматическим перезапуском при падении."""
        import re as _re

        while True:
            try:
                # Use absolute path — PATH may be stripped when launched from a .app
                cf_bin = _find_cloudflared() or "cloudflared"
                cmd = [cf_bin, "tunnel", "--url", f"{proto}://localhost:{port}", "--no-autoupdate"]
                # Self-signed cert → cloudflared не доверяет → 502 Bad Gateway
                if proto == "https":
                    cmd.append("--no-tls-verify")
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                url_found = False
                for line in proc.stdout:
                    line = line.strip()
                    if not url_found and ("trycloudflare.com" in line or "cfargotunnel.com" in line):
                        urls = _re.findall(r'https://[a-zA-Z0-9\-]+\.(?:trycloudflare\.com|cfargotunnel\.com)', line)
                        if urls:
                            url_found = True
                            # Wait for tunnel to stabilize before showing URL
                            time.sleep(10)
                            _p(f"\n  ╔══════════════════════════════════════════════════════╗", "green")
                            _p(f"  ║  🌍 Публичная ссылка:                                ║", "green")
                            _p(f"  ║  {urls[0]:<52s} ║", "cyan")
                            _p(f"  ╚══════════════════════════════════════════════════════╝", "green")
                            _p(f"  Отправьте эту ссылку пользователям.\n", "dim")
                            _tunnel_ready.set()

                # cloudflared завершился (сон Mac, обрыв сети)
                exit_code = proc.wait()
                _p(f"\n  ⚠ Cloudflare Tunnel отключился (код {exit_code}). Перезапуск через 5 сек...", "yellow")
                time.sleep(5)
                _p(f"  🌐 Перезапуск Cloudflare Tunnel...", "cyan")

            except Exception as e:
                _p(f"  ⚠ Cloudflare Tunnel ошибка: {e}. Повтор через 10 сек...", "yellow")
                time.sleep(10)

    try:
        tunnel_thread = threading.Thread(target=_run_tunnel_with_reconnect, daemon=True)
        tunnel_thread.start()
        return tunnel_thread

    except Exception as e:
        _p(f"  ⚠ Cloudflare Tunnel не запустился: {e}", "yellow")
        _p(f"  Установите: brew install cloudflared\n", "dim")
        return None


# ── Основной узел ─────────────────────────────────────────────────────────────

def cmd_run() -> None:
    _p(BANNER, "cyan")

    env     = _read_env()
    host    = "0.0.0.0"
    port    = int(env.get("PORT", "9000"))
    name    = env.get("DEVICE_NAME", platform.node())
    mode    = env.get("NETWORK_MODE", "local")
    ssl     = CERT_FILE.exists() and KEY_FILE.exists()
    proto   = "https" if ssl else "http"
    ip      = _local_ip()

    _p(f"  ⚡ Узел: {name}", "cyan")
    _p(f"  🔒 Режим: {'🌍 Глобальный' if mode == 'global' else '📡 Локальный'}")
    _p(f"  🌐 {proto}://localhost:{port}", "green")
    if ip != "127.0.0.1":
        _p(f"  📱 {proto}://{ip}:{port}  ← устройства в сети", "cyan")
    _p(f"  🔒 SSL: {'включён (' + str(CERT_FILE) + ')' if ssl else 'отключён'}")

    # Инвайт-режим
    invite = env.get("REGISTRATION_MODE", "open")
    if invite == "invite":
        code = env.get("INVITE_CODE_NODE", "")
        _p(f"  🔑 Регистрация: по инвайту ({code})", "yellow")
    elif invite == "closed":
        _p(f"  🔑 Регистрация: закрыта", "red")

    # Cloudflare Tunnel (автоматически в global mode)
    tunnel_proc = _start_cloudflare_tunnel(port, proto)
    if mode == "global" and not tunnel_proc:
        if not _has_cloudflared():
            _p("  ⚠ cloudflared не установлен — туннель не запущен", "yellow")
            _p("  Установите: brew install cloudflared", "dim")
        _p("")
    elif mode == "local":
        _p("  📌 Нажмите Ctrl+C для остановки\n", "dim")

    try:
        import uvicorn

        kwargs: dict = dict(
            app="app.main:app",
            host=host,
            port=port,
            reload=False,
            log_level="info",
            access_log=False,
        )
        if ssl:
            kwargs["ssl_certfile"] = str(CERT_FILE)
            kwargs["ssl_keyfile"]  = str(KEY_FILE)

        uvicorn.run(**kwargs)

    except ImportError as e:
        _p(f"✗ Ошибка импорта: {e}", "red")
        _p("  pip install -r requirements.txt", "yellow")
        sys.exit(1)
    except KeyboardInterrupt:
        _p("\n\n  ⛔ Узел остановлен.", "yellow")
    finally:
        if tunnel_proc:
            _p("  ⛔ Останавливаем Cloudflare Tunnel...", "dim")
            # Убиваем все процессы cloudflared (включая перезапущенные)
            try:
                subprocess.run(["pkill", "-f", "cloudflared tunnel"], timeout=5,
                               capture_output=True)
            except Exception:
                pass


# ── --invite ──────────────────────────────────────────────────────────────────

def cmd_invite() -> None:
    """Включает режим инвайт-кодов и генерирует/показывает код."""
    import secrets as _sec
    env = _read_env()
    code = env.get("INVITE_CODE_NODE")
    mode = env.get("REGISTRATION_MODE", "open")

    if code and mode == "invite":
        _p(f"\n  Инвайт-код уже настроен:", "green")
        _p(f"  ╔══════════════════════════════╗")
        _p(f"  ║  {code}  ║", "cyan")
        _p(f"  ╚══════════════════════════════╝")
        _p(f"\n  Режим: {mode}", "dim")
        _p(f"  Отправьте этот код тем кому разрешаете регистрацию.\n", "dim")
        return

    code = _sec.token_hex(8).upper()

    # Записываем в .env
    with open(ENV_FILE, "a") as f:
        f.write(f"\nREGISTRATION_MODE=invite\n")
        f.write(f"INVITE_CODE_NODE={code}\n")

    _p(f"\n  ✓ Режим инвайтов включён!", "green")
    _p(f"  ╔══════════════════════════════╗")
    _p(f"  ║  Инвайт-код: {code}  ║", "cyan")
    _p(f"  ╚══════════════════════════════╝")
    _p(f"\n  Без этого кода никто не сможет зарегистрироваться.", "dim")
    _p(f"  Отправьте код только тем кому доверяете.\n", "dim")
    _p(f"  Чтобы вернуть открытую регистрацию:", "dim")
    _p(f"  Измените в .env: REGISTRATION_MODE=open\n", "dim")


# ── Точка входа ───────────────────────────────────────────────────────────────

def main() -> None:
    _check_python()

    parser = argparse.ArgumentParser(
        prog="python run.py",
        description="⚡ VORTEX Node Launcher",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--setup",        action="store_true", help="Принудительно открыть мастер настройки")
    parser.add_argument("--status",       action="store_true", help="Показать статус узла")
    parser.add_argument("--reset",        action="store_true", help="Сбросить настройки")
    parser.add_argument("--no-browser",   action="store_true", help="Не открывать браузер автоматически")
    parser.add_argument("--wizard-port",  type=int, default=7979, metavar="PORT",
                        help="Порт мастера настройки (по умолчанию: 7979)")
    parser.add_argument("--generate-worker", action="store_true",
                        help="Сгенерировать Cloudflare Worker для CDN relay")
    parser.add_argument("--backend",     type=str, default="", metavar="URL",
                        help="URL бэкенда для CDN Worker (например: https://your-server.com:8000)")
    parser.add_argument("--invite",      action="store_true",
                        help="Включить режим инвайтов и показать/сгенерировать код")
    args = parser.parse_args()

    if args.invite:
        cmd_invite()

    elif args.generate_worker:
        cmd_generate_worker(args.backend)

    elif args.status:
        cmd_status()

    elif args.reset:
        cmd_reset()

    elif args.setup or not _is_initialized():
        cmd_setup(wizard_port=args.wizard_port, no_browser=args.no_browser)
        if _is_initialized():
            _p("\n✓ Настройка завершена! Запускаем узел...\n", "green")
            time.sleep(1)
            cmd_run()

    else:
        cmd_run()


if __name__ == "__main__":
    main()