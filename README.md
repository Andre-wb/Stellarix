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

*Без облаков. Без посредников. Только ты и твоя сеть.*

---

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/Rust-Cryptocore-CE4A00?style=for-the-badge&logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebRTC](https://img.shields.io/badge/WebRTC-P2P_Calls-333333?style=for-the-badge&logo=webrtc&logoColor=white)](https://webrtc.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge)](LICENSE)

</div>

---

## Что это?

VORTEX — мессенджер, который живёт целиком внутри твоей локальной сети (Wi-Fi или Ethernet). Никаких облачных серверов, никаких внешних зависимостей — только твои устройства и сквозное шифрование на уровне военного стандарта.

Запускаешь на двух ноутбуках в одной сети — они находят друг друга автоматически, через секунды. Все сообщения, звонки и файлы остаются внутри периметра сети и защищены так, что даже сам сервер не может их прочитать.

---

## Возможности

```
📡  Авто-обнаружение   UDP-broadcast — узлы находят друг друга сами
🔐  E2E шифрование     X25519 + AES-256-GCM для каждого сообщения и файла  
🏠  Комнаты            Публичные и приватные, до 200 участников
📁  Файлы              До 100 МБ, сжатие на клиенте, прогресс-бар
🎙️  Звонки             WebRTC голосовые и видео, прямые P2P каналы
🛡️  Встроенный WAF     SQLi, XSS, path traversal, rate limiting из коробки
🦀  Rust крипто        Argon2id, BLAKE3, AES-GCM — быстро и безопасно
🔄  Без интернета      Работает полностью в изолированной сети
```

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                       VORTEX NODE                        │
│                                                          │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────┐  │
│  │  JS Client  │────▶│  FastAPI     │────▶│  SQLite  │  │
│  │  (ES модули)│◀────│  + WebSocket │     │  (WAL)   │  │
│  └─────────────┘     └──────┬───────┘     └──────────┘  │
│         │                   │                            │
│    WebRTC P2P          ┌────▼─────┐                      │
│    (звонки)            │  Rust    │                      │
│                        │  Crypto  │                      │
│                        │  Core    │                      │
│                        └──────────┘                      │
└───────────────────────────┬─────────────────────────────┘
                            │ UDP broadcast
                  ┌─────────▼──────────┐
                  │   Другие узлы      │
                  │   в локальной сети │
                  └────────────────────┘
```

### Как работает шифрование

Сервер выступает **только** как сигнальный ретранслятор — он физически не может прочитать сообщения:

1. При подключении каждый клиент генерирует X25519 ключевую пару
2. Публичные ключи обмениваются через сервер
3. Каждая пара участников самостоятельно вычисляет `session_key = DH(priv_self, pub_peer)`
4. Все сообщения шифруются AES-256-GCM перед отправкой
5. Сервер видит только зашифрованный ciphertext — ключи у него никогда не было

---

## Стек технологий

| Слой | Технологии |
|------|-----------|
| **Клиент** | HTML5, CSS3, JavaScript ES-модули, WebSocket, WebRTC |
| **Сервер** | Python 3.10+, FastAPI, Uvicorn, SQLite WAL |
| **Криптография** | Rust / PyO3 — X25519, AES-256-GCM, Argon2id, BLAKE3, HKDF-SHA256 |
| **Безопасность** | JWT HS256, CSRF Double Submit Cookie, собственный WAF |
| **P2P сеть** | UDP broadcast discovery, HTTP P2P messaging, WebRTC STUN |

---

## Быстрый старт

### Требования

- Python **3.10+**
- Rust + Cargo (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- [maturin](https://github.com/PyO3/maturin) для сборки Rust-модуля

### Установка

```bash
# 1. Клонируй репозиторий
git clone https://github.com/yourname/vortex.git
cd vortex

# 2. Создай виртуальное окружение
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows

# 3. Установи Python-зависимости
pip install -r requirements.txt

# 4. Собери Rust криптоядро
maturin develop --release

# 5. Запусти
python run.py
```

Открой браузер: **http://localhost:8000**

### Тест децентрализации

Запусти второй узел на другом устройстве в той же сети (или на другом порту):

```bash
# Второй узел
PORT=8001 python run.py
```

Оба узла обнаружат друг друга автоматически через UDP-broadcast в течение ~2 секунд.

---

## Конфигурация

Создай `.env` в корне проекта (или переменные среды). При первом запуске секреты сгенерируются автоматически.

```env
# Безопасность — СМЕНИТЬ В ПРОДАКШНЕ
JWT_SECRET=<auto-generated>
CSRF_SECRET=<auto-generated>

# Токены
ACCESS_TOKEN_EXPIRE_MIN=1440
REFRESH_TOKEN_EXPIRE_DAYS=30

# Сервер
HOST=0.0.0.0
PORT=8000
DEVICE_NAME=           # имя узла для P2P (по умолчанию — hostname)

# Хранилище
DB_PATH=vortex.db
UPLOAD_DIR=uploads
MAX_FILE_MB=100

# P2P discovery
UDP_PORT=4200
UDP_INTERVAL_SEC=2
PEER_TIMEOUT_SEC=15

# WAF
WAF_RATE_LIMIT_REQUESTS=120
WAF_RATE_LIMIT_WINDOW=60
WAF_BLOCK_DURATION=3600
```

> ⚠️ В продакшне установи `ENVIRONMENT=production` — это включит HSTS, Secure cookies и строгий CSP.

---

## API

Интерактивная документация доступна по адресу **http://localhost:8000/api/docs**

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/api/authentication/register` | Регистрация |
| `POST` | `/api/authentication/login` | Вход |
| `GET` | `/api/authentication/me` | Текущий пользователь |
| `GET` | `/api/authentication/csrf-token` | CSRF токен |
| `POST` | `/api/rooms` | Создать комнату |
| `GET` | `/api/rooms/my` | Мои комнаты |
| `GET` | `/api/rooms/public` | Публичные комнаты |
| `POST` | `/api/rooms/join/{code}` | Вступить по коду |
| `GET` | `/api/rooms/{id}/members` | Участники комнаты |
| `POST` | `/api/files/upload/{room_id}` | Загрузить файл |
| `GET` | `/api/files/download/{file_id}` | Скачать файл |
| `GET` | `/api/peers` | Список узлов в сети |
| `WS` | `/ws/{room_id}` | Чат WebSocket |
| `WS` | `/ws/signal/{room_id}` | WebRTC сигнализация |

---

## Безопасность

| Слой | Реализация |
|------|-----------|
| **Аутентификация** | JWT HS256 + opaque refresh-токены (SHA-256 hash в БД) |
| **CSRF** | Double Submit Cookie — токен в cookie + заголовок `X-CSRF-Token` |
| **Пароли** | Argon2id (Rust) — стойкий к GPU/ASIC брутфорсу |
| **Шифрование** | X25519 DH + HKDF → AES-256-GCM для каждой сессии |
| **WAF** | SQLi, XSS, path traversal, null bytes, zip-bomb detection |
| **Заголовки** | CSP, HSTS, X-Frame-Options, Referrer-Policy и др. |
| **Rate limiting** | 120 запросов / 60 сек на IP, бан на 1 час при превышении |

---

## Структура проекта

```
vortex/
├── app/
│   ├── authentication/     # Регистрация, вход, JWT
│   ├── chats/              # WebSocket чат, комнаты, файлы
│   ├── peer/               # P2P discovery, connection manager
│   ├── security/           # WAF, middleware, крипто, валидация
│   └── utilites/           # Вспомогательные утилиты
├── rust_src/               # Rust криптоядро (vortex_chat)
├── static/
│   ├── css/                # Стили
│   └── js/                 # ES-модули клиента
│       └── chat/           # Модули чата (messages, file-upload, image-viewer)
├── templates/              # HTML шаблоны
├── keys/                   # X25519 ключи узла (auto-generated)
├── uploads/                # Загруженные файлы
├── run.py                  # Точка входа
└── requirements.txt
```

---

## Вклад в разработку

Pull Request'ы приветствуются. Для крупных изменений — сначала открой Issue для обсуждения.

```bash
git checkout -b feature/my-feature
git commit -m 'feat: add my feature'
git push origin feature/my-feature
# → открой Pull Request
```

---

## Лицензия

Распространяется под лицензией **Apache 2.0** — см. файл [LICENSE](LICENSE).

---

<div align="center">

**VORTEX** — сделан для свободного общения без границ и слежки.

*Твои данные принадлежат тебе.*

</div>
