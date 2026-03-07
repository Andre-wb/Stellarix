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
        port  = env.get("PORT", "8000")
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


# ── Мастер настройки ──────────────────────────────────────────────────────────

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


# ── Основной узел ─────────────────────────────────────────────────────────────

def cmd_run() -> None:
    _p(BANNER, "cyan")

    env     = _read_env()
    host    = env.get("HOST", "0.0.0.0")
    port    = int(env.get("PORT", "8000"))
    name    = env.get("DEVICE_NAME", platform.node())
    ssl     = CERT_FILE.exists() and KEY_FILE.exists()
    proto   = "https" if ssl else "http"
    ip      = _local_ip()

    _p(f"  ⚡ Узел: {name}", "cyan")
    _p(f"  🌐 {proto}://localhost:{port}", "green")
    if ip != "127.0.0.1":
        _p(f"  📱 {proto}://{ip}:{port}  ← другие устройства в сети", "cyan")
    _p(f"  🔒 SSL: {'включён (' + str(CERT_FILE) + ')' if ssl else 'отключён'}")
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
    args = parser.parse_args()

    if args.status:
        cmd_status()

    elif args.reset:
        cmd_reset()

    elif args.setup or not _is_initialized():
        cmd_setup(wizard_port=args.wizard_port, no_browser=args.no_browser)
        # После wizard-а — сразу запускаем узел
        if _is_initialized():
            _p("\n✓ Настройка завершена! Запускаем узел...\n", "green")
            time.sleep(1)
            cmd_run()

    else:
        cmd_run()


if __name__ == "__main__":
    main()