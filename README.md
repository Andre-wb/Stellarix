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

## Что такое VORTEX?

VORTEX — это мессенджер, который живёт внутри твоей локальной сети. Запускаешь на двух устройствах в одной Wi-Fi сети — они находят друг друга автоматически, через секунды. Ни один байт сообщений не покидает периметр сети.

Каждый участник — это **узел**. Нет центрального сервера, нет точки отказа, нет посредника, которому нужно доверять.

---

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/yourname/vortex.git
cd vortex

# 2. Окружение + зависимости
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Собрать Rust криптоядро
maturin develop --release

# 4. Запустить — при первом запуске откроется мастер настройки
python run.py
```

При первом запуске браузер автоматически откроет **мастер настройки узла** — там можно задать имя устройства, порт и сгенерировать SSL-сертификат. Всё через UI, никаких конфигов вручную.

Повторные запуски сразу стартуют узел:

```
  ⚡ Узел: MacBook-Boris
  🌐 https://localhost:8000
  🔒 SSL: включён (certs/vortex.crt)
```

---

## Мастер настройки

```bash
python run.py          # первый запуск → автоматически открывает wizard
python run.py --setup  # принудительно открыть wizard
python run.py --status # показать статус узла
python run.py --reset  # сбросить настройки

# Или запустить wizard напрямую из его папки:
python node_setup/run.py
python node_setup/run.py --port 9090 --no-browser
python node_setup/run.py --status
```

Wizard работает на временном порту `7979` и останавливается сам после завершения настройки.

---

## SSL — бесплатно, три варианта

Все варианты **бесплатны**. Выбор зависит от ситуации:

| Вариант | Интернет | Предупреждения браузера | Требования |
|---|---|---|---|
| **Самоподписанный** | ✗ не нужен | Первый раз, потом нет¹ | `pip install cryptography` |
| **mkcert** | ✗ не нужен | ✗ нет совсем | Установить `mkcert` |
| **Let's Encrypt** | ✓ нужен | ✗ нет совсем | Домен + открытый порт 80 |

> ¹ Wizard автоматически устанавливает CA в системное хранилище доверия (`security` на macOS, `certutil` на Windows, `update-ca-certificates` на Linux). После этого браузер считает сертификат доверенным.

HTTPS обязателен для корректной работы WebRTC-звонков, микрофона и камеры в браузере.

---

## Архитектура

```
┌─────────────────────── VORTEX NODE ────────────────────────┐
│                                                             │
│   Browser Client          FastAPI Server       SQLite WAL  │
│   ┌───────────┐    WS     ┌────────────┐      ┌─────────┐  │
│   │ JS (ESM)  │◀────────▶│  Uvicorn   │─────▶│  vortex │  │
│   │ WebRTC    │   HTTPS   │  + WAF     │      │  .db    │  │
│   └───────────┘           └─────┬──────┘      └─────────┘  │
│                                 │                           │
│                          ┌──────▼──────┐                   │
│                          │  Rust Core  │                   │
│                          │  vortex_chat│                   │
│                          └─────────────┘                   │
└──────────────────────────────┬──────────────────────────────┘
                               │ UDP broadcast :4200
              ┌────────────────┼────────────────┐
              │                │                │
         Node A            Node B            Node C
       (ноутбук)         (Raspberry Pi)     (телефон)
```

### Как работает E2E шифрование

Сервер не может прочитать сообщения — ни технически, ни теоретически:

```
Alice                          Server                         Bob
  │                              │                              │
  │── pub_key_alice ────────────▶│── pub_key_alice ────────────▶│
  │◀─ pub_key_bob ───────────────│◀─ pub_key_bob ───────────────│
  │                              │                              │
  │  session_key =               │   видит только:              │  session_key =
  │  X25519(priv_alice,          │   зашифрованный              │  X25519(priv_bob,
  │         pub_bob)             │   ciphertext                 │         pub_alice)
  │                              │                              │
  │══ AES-256-GCM(msg) ═════════▶│══ AES-256-GCM(msg) ═════════▶│
```

Ключи никогда не покидают устройства. Сервер — только ретранслятор зашифрованного трафика.

---

## P2P обнаружение узлов

При запуске каждый узел начинает слать UDP-broadcast каждые 2 секунды:

```json
{ "name": "MacBook-Boris", "port": 8000 }
```

Соседние узлы в сети отвечают и появляются на вкладке «📡 Устройства в сети». Никакого центрального реестра, никакого DNS — чистый broadcast на `192.168.X.255:4200`.

---

## Возможности

```
📡  Авто-обнаружение    UDP broadcast, работает без интернета
🔐  E2E шифрование      X25519 + HKDF + AES-256-GCM для каждой сессии
🏠  Комнаты             Публичные и приватные, до 200 участников
📁  Файлы               До 100 МБ, зашифрованы, SHA-256 проверка
🎙️  Звонки              WebRTC голос и видео, прямые P2P-каналы
🛡️  WAF                 SQLi, XSS, path traversal, rate limiting
🦀  Rust крипто         Argon2id, BLAKE3, AES-GCM, X25519
🔒  SSL из коробки      Wizard генерирует сертификат при первом запуске
```

---

## Стек

| Слой | Технологии |
|---|---|
| **Клиент** | HTML5, CSS3, JavaScript ES-модули, WebSocket, WebRTC |
| **Сервер** | Python 3.10+, FastAPI, Uvicorn, SQLite WAL |
| **Криптография** | Rust / PyO3 — X25519, AES-256-GCM, Argon2id, BLAKE3, HKDF |
| **Безопасность** | JWT HS256, CSRF Double Submit Cookie, WAF middleware |
| **P2P** | UDP broadcast discovery, HTTP direct messaging, WebRTC STUN |
| **Setup** | FastAPI wizard, cryptography (self-signed CA), mkcert, certbot |

---

## Структура проекта

```
Vortex/
├── run.py                    ← точка входа: wizard при первом запуске, иначе узел
│
├── node_setup/               ← мастер настройки узла
│   ├── run.py                ← автономный запуск wizard-а
│   ├── wizard.py             ← FastAPI сервер wizard-а
│   ├── ssl_manager.py        ← генерация SSL (self-signed / mkcert / Let's Encrypt)
│   ├── templates/
│   │   └── setup.html        ← UI мастера (чистый HTML)
│   └── static/
│       ├── css/setup.css     ← стили wizard-а
│       └── js/setup.js       ← логика wizard-а
│
├── app/
│   ├── authentication/       ← JWT, регистрация, вход
│   ├── chats/                ← WebSocket чат, комнаты, файлы
│   ├── peer/                 ← P2P discovery, peer registry
│   └── security/             ← WAF, крипто, CSRF
│
├── static/                   ← фронтенд основного приложения
│   ├── css/
│   └── js/
│
├── templates/                ← Jinja2 шаблоны основного приложения
├── rust_utils/                 ← Rust криптоядро (vortex_chat)
    ├── src/
        ├── auth/
        ├── crypto/
        ├── messages/
        ├── udp_broadcast/
        ├── auth.rs
        ├── crypto.rs
        ├── lib.rs
        ├── messages.rs
        ├── udp_broadcasts.rs
    ├── target/
    ├── tests/
    ├── Cargo.lock
    ├── Cargo.toml
├── certs/                    ← SSL сертификаты (создаётся автоматически)
├── keys/                     ← X25519 ключи узла (создаётся автоматически)
├── uploads/                  ← загруженные файлы
├── .env                      ← конфигурация (создаётся wizard-ом)
└── requirements.txt
```

---

## Конфигурация

Файл `.env` создаётся автоматически через wizard. При необходимости можно редактировать вручную:

```env
# Безопасность — генерируются автоматически, не менять без необходимости
JWT_SECRET=<hex-64>
CSRF_SECRET=<hex-64>

# Сервер
HOST=0.0.0.0
PORT=8000
DEVICE_NAME=MacBook-Boris

# Хранилище
DB_PATH=vortex.db
UPLOAD_DIR=uploads
MAX_FILE_MB=100

# P2P Discovery
UDP_PORT=4200
UDP_INTERVAL_SEC=2
PEER_TIMEOUT_SEC=15

# WAF
WAF_RATE_LIMIT_REQUESTS=120
WAF_BLOCK_DURATION=3600
```

---

## API

Интерактивная документация: **https://localhost:8000/api/docs**

| Метод | Endpoint | Описание |
|---|---|---|
| `POST` | `/api/authentication/register` | Регистрация |
| `POST` | `/api/authentication/login` | Вход |
| `GET`  | `/api/authentication/me` | Текущий пользователь |
| `POST` | `/api/rooms` | Создать комнату |
| `GET`  | `/api/rooms/my` | Мои комнаты |
| `POST` | `/api/rooms/join/{code}` | Вступить по коду |
| `POST` | `/api/files/upload/{room_id}` | Загрузить файл |
| `GET`  | `/api/files/download/{file_id}` | Скачать файл |
| `GET`  | `/api/peers` | Список узлов в сети |
| `WS`   | `/ws/{room_id}` | Чат WebSocket |
| `WS`   | `/ws/signal/{room_id}` | WebRTC сигнализация |

---

## Безопасность

| Механизм | Реализация |
|---|---|
| **Аутентификация** | JWT HS256 + opaque refresh-токены, SHA-256 в БД |
| **CSRF** | Double Submit Cookie — токен в cookie + заголовок |
| **Пароли** | Argon2id (Rust) — GPU/ASIC-стойкий |
| **Шифрование** | X25519 DH → HKDF → AES-256-GCM, новый ключ на каждую сессию |
| **Файлы** | SHA-256 проверка целостности при скачивании |
| **WAF** | SQLi, XSS, path traversal, null bytes, rate limiting |
| **Заголовки** | CSP, HSTS, X-Frame-Options, Referrer-Policy |

---

## Требования

- Python **3.10+**
- Rust + Cargo — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- maturin — `pip install maturin`
- *(опционально)* mkcert для SSL без предупреждений браузера

---

## Вклад в разработку

```bash
git checkout -b feature/my-feature
git commit -m 'feat: описание изменения'
git push origin feature/my-feature
# → открой Pull Request
```

---

## Лицензия

Распространяется под лицензией **Apache 2.0** — см. файл [LICENSE](LICENSE).

---

<div align="center">

VORTEX — сделан для свободного общения без слежки и посредников.

*Твои данные принадлежат тебе.*

</div>