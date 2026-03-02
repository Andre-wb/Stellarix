<div align="center">

```
                                                                ██╗   ██╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗
                                                                ██║   ██║██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝
                                                                ██║   ██║██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝ 
                                                                ╚██╗ ██╔╝██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗ 
                                                                 ╚████╔╝ ╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗
                                                                  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
```

**Децентрализованный мессенджер для локальных сетей**

Без облаков. Без серверов. Только твоя сеть.

---

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/Rust-Crypto_Core-CE4A00?style=for-the-badge&logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebRTC](https://img.shields.io/badge/WebRTC-P2P_Calls-333333?style=for-the-badge&logo=webrtc&logoColor=white)](https://webrtc.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge)](LICENSE)

</div>

---

## ⚡️ Что такое VORTEX?

VORTEX — это мессенджер, который живёт **внутри твоей локальной сети**. Запускаешь на двух устройствах в одной Wi-Fi сети — они находят друг друга автоматически, через секунды. Ни один байт сообщений не покидает периметр сети.

Каждый участник — это **узел**. Нет центрального сервера, нет точки отказа, нет посредника, которому нужно доверять.

```
  Ноутбук ──── Wi-Fi ──── Raspberry Pi
     │                        │
     └──────── вместе ────────┘
           без интернета
```

---

## ⚡ Возможности

```
📡  Авто-обнаружение    UDP broadcast, работает без интернета
🔐  E2E шифрование      X25519 + HKDF + AES-256-GCM для каждой сессии
🏠  Комнаты             Публичные и приватные, до 200 участников
📁  Файлы               До 100 МБ, зашифрованы, SHA-256 проверка целостности
🎙️  Звонки              WebRTC голос и видео, прямые P2P-каналы
🛡️  WAF                 SQLi, XSS, path traversal, rate limiting
🦀  Rust крипто         Argon2id, BLAKE3, AES-GCM, X25519
🔒  SSL из коробки      Wizard генерирует сертификат при первом запуске
```

---

## 📋 Содержание

- [Установка зависимостей](#установка-зависимостей)
- [Установка проекта](#установка-проекта)
- [Запуск](#запуск)
- [Настройка SSL](#настройка-ssl)
- [Конфигурация](#конфигурация)
- [Архитектура](#архитектура)
- [API](#api)
- [Безопасность](#безопасность)
- [Структура проекта](#структура-проекта)

---

## 🛠 Установка зависимостей

### Git

<details>
<summary><b>Windows</b></summary>

1. Скачай установщик с [git-scm.com/download/win](https://git-scm.com/download/win)
2. Запусти `.exe`, оставь все настройки по умолчанию
3. Проверь:
   ```cmd
   git --version
   ```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install git
# или через Xcode Command Line Tools:
xcode-select --install
```

</details>

<details>
<summary><b>Linux (Ubuntu / Debian)</b></summary>

```bash
sudo apt update && sudo apt install git -y
git --version
```

</details>

---

### Python 3.10+

<details>
<summary><b>Windows</b></summary>

1. Скачай с [python.org/downloads](https://www.python.org/downloads/)
2. При установке поставь галочку **"Add Python to PATH"**
3. Проверь:
   ```cmd
   python --version
   ```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install python@3.12
python3 --version
```

</details>

<details>
<summary><b>Linux (Ubuntu / Debian)</b></summary>

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv -y
python3 --version
```

</details>

---

### Rust + Cargo

Нужен для компиляции криптоядра (X25519, AES-GCM, Argon2id).

<details>
<summary><b>macOS / Linux</b></summary>

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
rustc --version && cargo --version
```

</details>

<details>
<summary><b>Windows</b></summary>

1. Скачай `rustup-init.exe` с [rustup.rs](https://rustup.rs/)
2. Запусти, выбери вариант **1 (default)**
3. Также потребуется [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/) — rustup предложит установить автоматически
4. Перезапусти терминал и проверь:
   ```cmd
   rustc --version
   cargo --version
   ```

</details>

---

### mkcert — SSL без предупреждений браузера

<details>
<summary><b>Windows</b></summary>

```powershell
# Через Chocolatey
choco install mkcert

# Через Scoop
scoop install mkcert

# Вручную:
# 1. Скачай mkcert-v*.exe с https://github.com/FiloSottile/mkcert/releases
# 2. Переименуй в mkcert.exe и положи в папку из PATH
mkcert --version
```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install mkcert
brew install nss    # нужно для Firefox
mkcert --version
```

</details>

<details>
<summary><b>Linux (Ubuntu / Debian)</b></summary>

```bash
# Через apt (Ubuntu 22.04+)
sudo apt install mkcert -y

# Или вручную
curl -Lo mkcert https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-v1.4.4-linux-amd64
chmod +x mkcert && sudo mv mkcert /usr/local/bin/
mkcert --version
```

</details>

---

### maturin — сборщик Rust → Python

```bash
pip install maturin
maturin --version
```

---

## 📦 Установка проекта

```bash
# 1. Клонировать
git clone https://github.com/Andre-wb/Vortex.git
cd Vortex

# 2. Создать виртуальное окружение
python -m venv .venv

# Активация:
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows CMD
.venv\Scripts\Activate.ps1       # Windows PowerShell

# 3. Установить Python зависимости
pip install -r requirements.txt

# 4. Скомпилировать Rust криптоядро
cd rust_utils
maturin develop --release
cd ..
```

> **Первая компиляция Rust занимает 1–3 минуты** — это нормально, следующие пересборки гораздо быстрее.

---

## 🚀 Запуск

```bash
python run.py
```

**При первом запуске** браузер автоматически откроет **мастер настройки** на `http://localhost:7979`. Задай имя устройства, порт и сгенерируй SSL-сертификат. Wizard завершается сам.

**При повторных запусках** узел стартует сразу:

```
  ⚡ Vortex Node — MacBook-Boris
  🌐 https://localhost:8000
  🔒 SSL: certs/vortex.crt
  📡 P2P Discovery: UDP :4200
```

### Все команды

```bash
python run.py                   # запуск (wizard при первом старте)
python run.py --setup           # принудительно открыть мастер настройки
python run.py --status          # статус узла и список пиров в сети
python run.py --reset           # сбросить все настройки и сертификаты
```

### Несколько узлов на одной машине (для тестирования)

```bash
# Терминал 1
PORT=8001 DEVICE_NAME=Node-Alice python run.py

# Терминал 2
PORT=8002 DEVICE_NAME=Node-Bob python run.py
```

Узлы обнаружат друг друга через UDP broadcast в течение ~2 секунд.

---

## 🔒 Настройка SSL

HTTPS обязателен для WebRTC-звонков (браузер блокирует микрофон/камеру без HTTPS). Три варианта:

| Вариант | Интернет | Предупреждения браузера | Сложность |
|---|---|---|---|
| **Самоподписанный** | ✗ не нужен | Один раз, потом исчезает | ⭐ просто |
| **mkcert** | ✗ не нужен | ✗ нет совсем | ⭐⭐ легко |
| **Let's Encrypt** | ✓ нужен + домен | ✗ нет совсем | ⭐⭐⭐ сложнее |

### Вариант 1 — Самоподписанный (по умолчанию)

Wizard генерирует сертификат автоматически и устанавливает его в системное хранилище:

- **macOS** → `security add-trusted-cert`
- **Windows** → `certutil -addstore Root`
- **Linux** → `update-ca-certificates`

После этого браузер принимает сертификат без предупреждений.

### Вариант 2 — mkcert (рекомендуется)

```bash
# Установить локальный CA (один раз на устройство)
mkcert -install

# Сгенерировать сертификат
mkcert -cert-file certs/vortex.crt -key-file certs/vortex.key \
       localhost 127.0.0.1 ::1 $(hostname -I | awk '{print $1}')
```

### Вариант 3 — Let's Encrypt / Certbot

```bash
sudo apt install certbot -y
sudo certbot certonly --standalone -d yourdomain.com

sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem certs/vortex.crt
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   certs/vortex.key
sudo chown $USER certs/vortex.crt certs/vortex.key
```

---

## ⚙️ Конфигурация

`.env` создаётся wizard-ом автоматически:

```env
# ─── Безопасность ────────────────────────────────────────
JWT_SECRET=<hex-64>          # генерируется автоматически
CSRF_SECRET=<hex-64>         # генерируется автоматически

# ─── Сервер ──────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
DEVICE_NAME=MacBook-Boris

# ─── Хранилище ───────────────────────────────────────────
DB_PATH=vortex.db
UPLOAD_DIR=uploads
MAX_FILE_MB=100

# ─── P2P Discovery ───────────────────────────────────────
UDP_PORT=4200
UDP_INTERVAL_SEC=2
PEER_TIMEOUT_SEC=15

# ─── WAF ─────────────────────────────────────────────────
WAF_RATE_LIMIT_REQUESTS=120
WAF_BLOCK_DURATION=3600

# ─── Флаг инициализации ──────────────────────────────────
NODE_INITIALIZED=true
```

---

## 🏗 Архитектура

```
┌─────────────────────── VORTEX NODE ────────────────────────┐
│                                                            │
│   Browser Client          FastAPI Server       SQLite WAL  │
│   ┌───────────┐    WS     ┌────────────┐      ┌─────────┐  │
│   │ JS (ESM)  │◀────────▶ │  Uvicorn   │────▶ │ vortex  │  │
│   │ WebRTC    │   HTTPS   │  + WAF     │      │   .db   │  │
│   └───────────┘           └─────┬──────┘      └─────────┘  │
│                                 │                          │
│                          ┌──────▼──────┐                   │
│                          │  Rust Core  │                   │
│                          │ vortex_chat │                   │
│                          └─────────────┘                   │
└──────────────────────────────┬─────────────────────────────┘
                               │ UDP broadcast :4200
              ┌────────────────┼────────────────┐
              │                │                │
         Node A            Node B            Node C
       (ноутбук)       (Raspberry Pi)      (телефон)
```

### P2P обнаружение узлов

Каждые 2 секунды узел шлёт UDP broadcast:

```json
{ "name": "MacBook-Boris", "port": 8000 }
```

Соседи слушают порт `4200` и добавляют источник в реестр. Исчезнувший узел удаляется через 15 секунд. Если Rust модуль скомпилирован — использует `vortex_chat.start_discovery()`, иначе автоматически включается Python fallback.

### E2E шифрование

```
Alice                       Server                      Bob
  │── pub_key ─────────────▶│── pub_key ────────────────▶│
  │◀─ pub_key ──────────────│◀─ pub_key ─────────────────│
  │                         │                            │
  │  key = X25519(          │  видит только              │  key = X25519(
  │    priv_alice, pub_bob) │  зашифрованный ciphertext  │    priv_bob, pub_alice)
  │                         │                            │
  │══ AES-256-GCM ═════════▶│══ AES-256-GCM ════════════▶│
```

Приватные ключи никогда не покидают устройства. Новый сессионный ключ — на каждый диалог.

---

## 🔌 API

Интерактивная документация: **`https://localhost:8000/api/docs`**

| Метод | Endpoint | Описание |
|---|---|---|
| `POST` | `/api/authentication/register` | Регистрация |
| `POST` | `/api/authentication/login` | Вход |
| `GET`  | `/api/authentication/me` | Текущий пользователь |
| `POST` | `/api/rooms` | Создать комнату |
| `GET`  | `/api/rooms/my` | Мои комнаты |
| `POST` | `/api/rooms/join/{code}` | Вступить по коду приглашения |
| `POST` | `/api/files/upload/{room_id}` | Загрузить файл |
| `GET`  | `/api/files/download/{file_id}` | Скачать файл |
| `GET`  | `/api/files/peer/{file_id}` | Скачать файл с соседнего узла (P2P) |
| `GET`  | `/api/peers` | Список активных узлов |
| `GET`  | `/api/peers/status` | Публичный статус узла (без авторизации) |
| `POST` | `/api/peers/receive` | Принять P2P сообщение от соседнего узла |
| `WS`   | `/ws/{room_id}` | WebSocket чата |
| `WS`   | `/ws/signal/{room_id}` | WebRTC сигнализация |

---

## 🛡 Безопасность

| Механизм | Реализация |
|---|---|
| **Аутентификация** | JWT HS256 + opaque refresh-токены, SHA-256 хэш в БД |
| **CSRF** | Double Submit Cookie — токен в `HttpOnly` cookie + заголовок |
| **Пароли** | Argon2id (Rust) — GPU/ASIC-стойкое хэширование |
| **E2E шифрование** | X25519 DH → HKDF → AES-256-GCM, уникальный ключ на сессию |
| **Файлы** | SHA-256 проверка целостности при каждом скачивании |
| **WAF** | Блокировка SQLi, XSS, path traversal, null bytes |
| **Rate limiting** | 120 req/min на IP, блокировка на 1 час при превышении |
| **HTTP заголовки** | CSP, HSTS, X-Frame-Options, Referrer-Policy |

---

## 📁 Структура проекта

```
Vortex/
├── run.py                      ← точка входа
│
├── node_setup/                 ← мастер настройки
│   ├── run.py
│   ├── wizard.py               ← FastAPI сервер wizard-а (порт 7979)
│   ├── ssl_manager.py          ← self-signed / mkcert / certbot
│   ├── templates/setup.html
│   └── static/
│       ├── css/setup.css
│       └── js/setup.js
│
├── app/
│   ├── main.py                 ← FastAPI app + WAF middleware
│   ├── config.py               ← Config из .env
│   ├── models.py               ← SQLAlchemy модели
│   ├── authentication/         ← JWT, регистрация, вход
│   ├── chats/                  ← WebSocket, комнаты, файлы
│   ├── peer/                   ← P2P discovery, peer registry, WS manager
│   └── security/               ← WAF, CSRF, крипто-утилиты
│
├── rust_utils/                 ← Rust криптоядро
│   ├── src/
│   │   ├── lib.rs
│   │   ├── crypto.rs           ← X25519, AES-GCM, HKDF
│   │   ├── auth.rs             ← Argon2id, BLAKE3
│   │   ├── messages.rs
│   │   └── udp_broadcasts.rs
│   └── Cargo.toml
│
├── static/                     ← фронтенд
├── templates/                  ← Jinja2 шаблоны
│
├── certs/                      ← SSL сертификаты (создаётся автоматически)
├── keys/                       ← X25519 ключи узла (создаётся автоматически)
├── uploads/                    ← загруженные файлы
├── .env                        ← конфигурация (создаётся wizard-ом)
└── requirements.txt
```

---

## 🤝 Вклад в разработку

```bash
git checkout -b feature/my-feature
git commit -m 'feat: описание изменения'
git push origin feature/my-feature
# → открой Pull Request
```

---

## 📄 Лицензия

Распространяется под лицензией **Apache 2.0** — см. файл [LICENSE](LICENSE).

---

<div align="center">

VORTEX — сделан для свободного общения без слежки и посредников.

*Твои данные принадлежат тебе.*

</div>
