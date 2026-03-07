<div align="center">

```
██╗   ██╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗
██║   ██║██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝
██║   ██║██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝ 
╚██╗ ██╔╝██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗ 
 ╚████╔╝ ╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗
  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
```

**Децентрализованный P2P мессенджер с E2E шифрованием**

Без облаков. Без серверов. Без интернета. Только твоя сеть.

---

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/Rust-Crypto_Core-CE4A00?style=for-the-badge&logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebRTC](https://img.shields.io/badge/WebRTC-P2P_Calls-333333?style=for-the-badge&logo=webrtc&logoColor=white)](https://webrtc.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge)](LICENSE)

</div>

---

## ⚡ Что такое VORTEX?

VORTEX — мессенджер, который живёт **внутри локальной сети**. Запускаешь на двух устройствах в одной Wi-Fi сети — они находят друг друга автоматически, за секунды. Ни один байт сообщений не покидает периметр сети.

Каждый участник — это **узел**. Нет центрального сервера, нет единой точки отказа, нет посредника, которому нужно доверять.

```
  Ноутбук ──── Wi-Fi ──── Raspberry Pi ──── Телефон
     │                         │                │
     └─────────── mesh ─────────┘────────────────┘
                     без интернета
```

---

## 🆚 VORTEX vs аналоги

> Почему не Signal, Telegram или Briar?

| Функция | **VORTEX** | Signal | Telegram | Briar | Element (Matrix) |
|---|:---:|:---:|:---:|:---:|:---:|
| **Работает без интернета** | ✅ полностью | ❌ | ❌ | ✅ частично | ❌ |
| **E2E шифрование по умолчанию** | ✅ всегда | ✅ | ⚠️ только «секретные чаты» | ✅ | ⚠️ только включив |
| **Нет центрального сервера** | ✅ | ❌ серверы Signal | ❌ серверы Telegram | ✅ | ⚠️ федерированные серверы |
| **Открытый криптокод** | ✅ Rust | ✅ | ❌ | ✅ | ✅ |
| **LAN авто-обнаружение** | ✅ UDP ~2 сек | ❌ | ❌ | ✅ медленно | ❌ |
| **BLE (Bluetooth)** | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Wi-Fi Direct P2P** | ✅ | ❌ | ❌ | ✅ Android only | ❌ |
| **NAT Traversal (STUN)** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Аудио/видео звонки** | ✅ WebRTC | ✅ | ✅ | ❌ | ✅ |
| **Мониторинг RTT/Jitter/Loss** | ✅ реальное время | ❌ | ❌ | ❌ | ❌ |
| **Групповые комнаты** | ✅ до 200 чел | ✅ | ✅ | ✅ | ✅ |
| **Файлы** | ✅ до 100 МБ | ✅ | ✅ | ⚠️ до 10 МБ | ✅ |
| **Голосовые сообщения** | ✅ waveform | ✅ | ✅ | ❌ | ✅ |
| **Федерация узлов** | ✅ мультихоп A→B→C | ❌ | ❌ | ❌ | ✅ |
| **Встроенный WAF** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Веб-интерфейс** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Самостоятельный хостинг** | ✅ один файл | ❌ | ❌ | ✅ | ✅ сложно |
| **Номер телефона обязателен** | ❌ | ✅ | ✅ | ❌ | ❌ |
| **Производительность крипто** | ✅ Rust native | ✅ C++ | ✅ | ⚠️ Java | ⚠️ JS |

### Ключевые отличия от ближайших аналогов

**Vs Signal** — Signal требует номер телефона, требует интернет и работает через американские серверы Signal Foundation. VORTEX работает полностью офлайн без каких-либо идентификаторов личности.

**Vs Briar** — Briar тоже работает в LAN/BLE, но это Android-only приложение без веб-интерфейса, без видеозвонков, без файлов >10 МБ. VORTEX кроссплатформенный (Web + Linux + Windows) и значительно более функциональный.

**Vs Telegram** — Telegram хранит сообщения в облаке в незашифрованном виде (если не «секретный чат»), требует интернет, централизован. VORTEX — противоположность по всем параметрам.

**Vs Element/Matrix** — Matrix децентрализован, но всё равно требует интернет для общения между серверами и сложен в настройке. VORTEX готов к работе через `python run.py` за минуту.

---

## ✨ Возможности

| Функция | Детали |
|---|---|
| 📡 **Авто-обнаружение** | UDP broadcast :4200, находит соседей за ~2 сек, таймаут пира 15 сек |
| 🔐 **E2E шифрование** | X25519 + HKDF-SHA256 + AES-256-GCM, уникальный ключ на каждую комнату |
| 🏠 **Комнаты** | Публичные и приватные, до 200 участников, инвайт-коды (8 символов) |
| 📁 **Файлы** | До 100 МБ, SHA-256 контроль целостности, XHR upload с прогрессом |
| 🎙️ **Звонки** | WebRTC голос + видео, P2P медиапоток (сервер не участвует) |
| 📊 **Качество звонка** | getStats() каждые 2 сек: RTT, джиттер, потери пакетов, битрейт, тип ICE |
| 🔀 **Мультихоп** | Федерация A→B→C, TTL защита от петель, дедупликация по msg_id |
| 🛡️ **WAF** | SQLi, XSS, path traversal, null bytes, rate limiting, auto-ban |
| 🦀 **Rust крипто** | Argon2id, BLAKE3, AES-GCM, X25519 — нативная скорость, PyO3 биндинги |
| 🔒 **SSL из коробки** | Wizard генерирует сертификат при первом запуске, поддержан mkcert |
| 🌐 **NAT Traversal** | STUN + UDP Hole Punching (RFC 5389), 4 STUN-сервера |
| 📶 **Wi-Fi Direct** | P2P без точки доступа: Linux (wpa_supplicant), Windows (WinRT) |
| 🔵 **BLE fallback** | Bluetooth LE discovery + сообщения при недоступности Wi-Fi |
| 🎨 **UI** | Glassmorphism, liquid-glass эффекты, тёмная тема, photo editor |
| 📱 **PWA** | Устанавливается как приложение на Win/Mac/Linux/Android/iOS, офлайн-кэш, push-уведомления |

---

## 📋 Содержание

- [VORTEX vs аналоги](#-vortex-vs-аналоги)
- [Установка зависимостей](#-установка-зависимостей)
- [Установка проекта](#-установка-проекта)
- [Запуск](#-запуск)
- [Настройка SSL](#-настройка-ssl)
- [Конфигурация](#-конфигурация)
- [Архитектура](#-архитектура)
- [E2E шифрование — как это работает](#-e2e-шифрование--как-это-работает)
- [Мониторинг качества звонков](#-мониторинг-качества-звонков)
- [Транспортный стек](#-транспортный-стек)
- [Протоколы](#-протоколы)
- [API](#-api)
- [Безопасность и модель угроз](#-безопасность-и-модель-угроз)
- [Надёжность](#-надёжность)
- [PWA — установка как приложение](#-pwa--установка-как-приложение)
- [Метрики и производительность](#-метрики-и-производительность)
- [Тестирование](#-тестирование)
- [Структура проекта](#-структура-проекта)

---

## 🛠 Установка зависимостей

### Git

<details>
<summary><b>Windows</b></summary>

1. Скачай установщик с [git-scm.com/download/win](https://git-scm.com/download/win)
2. Запусти `.exe`, оставь настройки по умолчанию
3. Проверь: `git --version`

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
```

</details>

---

### Python 3.10+

<details>
<summary><b>Windows</b></summary>

1. Скачай с [python.org/downloads](https://www.python.org/downloads/)
2. При установке поставь галочку **"Add Python to PATH"**
3. Проверь: `python --version`

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install python@3.12
```

</details>

<details>
<summary><b>Linux (Ubuntu / Debian)</b></summary>

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv -y
```

</details>

---

### Rust + Cargo

Нужен для компиляции криптоядра (X25519, AES-GCM, Argon2id, BLAKE3).

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
3. Также потребуется [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
4. Перезапусти терминал и проверь: `rustc --version && cargo --version`

</details>

---

### mkcert — SSL без предупреждений браузера

<details>
<summary><b>Windows</b></summary>

```powershell
choco install mkcert   # через Chocolatey
# или: scoop install mkcert
```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install mkcert && brew install nss
```

</details>

<details>
<summary><b>Linux</b></summary>

```bash
sudo apt install mkcert -y
# или вручную:
curl -Lo mkcert https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-v1.4.4-linux-amd64
chmod +x mkcert && sudo mv mkcert /usr/local/bin/
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
export RUSTFLAGS="-L /opt/homebrew/opt/python@3.13/Frameworks/Python.framework/Versions/3.13/lib -lpython3.13"
maturin build
cd ..
```

> **Первая компиляция Rust занимает 1–3 минуты** — последующие пересборки значительно быстрее.

---

## 🚀 Запуск

```bash
python run.py
```

**При первом запуске** браузер откроет **мастер настройки** на `http://localhost:7979`. Задай имя устройства, порт, сгенерируй SSL-сертификат. Wizard завершится сам.

**При повторных запусках** узел стартует сразу:

```
  ⚡ Vortex Node — Имя-Устройства
  🌐 https://localhost:8000
  📱 https://000.000.000.000:8000  ← другие устройства в сети
  🔒 SSL: certs/vortex.crt
  🦀 Rust crypto: vortex_chat 0.1.2
  🌐 STUN: external 223.204.221.114:62556
  📡 BLE транспорт запущен
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

HTTPS обязателен для WebRTC-звонков (браузер блокирует микрофон/камеру без HTTPS).

| Вариант | Интернет | Предупреждения браузера | Сложность |
|---|---|---|---|
| **Самоподписанный** | ✗ не нужен | Один раз при первом открытии | ⭐ просто |
| **mkcert** | ✗ не нужен | ✗ нет совсем | ⭐⭐ легко |
| **Let's Encrypt** | ✓ нужен + домен | ✗ нет совсем | ⭐⭐⭐ сложнее |

### Вариант 1 — Самоподписанный (по умолчанию)

Wizard генерирует сертификат автоматически и устанавливает в системное хранилище:
- **macOS** → `security add-trusted-cert`
- **Windows** → `certutil -addstore Root`
- **Linux** → `update-ca-certificates`

### Вариант 2 — mkcert (рекомендуется)

```bash
mkcert -install   # один раз на устройство

mkcert -cert-file certs/vortex.crt -key-file certs/vortex.key \
       localhost 127.0.0.1 ::1 $(hostname -I | awk '{print $1}')
```

### Вариант 3 — Let's Encrypt / Certbot

```bash
sudo certbot certonly --standalone -d yourdomain.com
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem certs/vortex.crt
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   certs/vortex.key
```

---

## ⚙️ Конфигурация

`.env` создаётся wizard-ом автоматически:

```env
# ─── Безопасность ─────────────────────────────────────────
JWT_SECRET=<hex-64>           # генерируется автоматически
CSRF_SECRET=<hex-64>          # генерируется автоматически

# ─── Сервер ───────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
DEVICE_NAME=MacBook-Boris

# ─── Хранилище ────────────────────────────────────────────
DB_PATH=vortex.db
UPLOAD_DIR=uploads
MAX_FILE_MB=100

# ─── P2P Discovery ────────────────────────────────────────
UDP_PORT=4200
UDP_INTERVAL_SEC=2
PEER_TIMEOUT_SEC=15

# ─── WAF ──────────────────────────────────────────────────
WAF_RATE_LIMIT_REQUESTS=120
WAF_BLOCK_DURATION=3600

# ─── Флаг инициализации ───────────────────────────────────
NODE_INITIALIZED=true
```

---

## 🏗 Архитектура

Подробные диаграммы — в файле [`ARCHITECTURE.md`](ARCHITECTURE.md).

```
┌─────────────────────────── VORTEX NODE ─────────────────────────────┐
│                                                                      │
│   Browser Client               FastAPI Server          SQLite WAL   │
│   ┌──────────────┐  WS/WSS    ┌───────────────┐      ┌──────────┐  │
│   │  JS (ESM)    │◀──────────▶│   Uvicorn     │────▶ │ vortex   │  │
│   │  WebRTC      │   HTTPS    │   + WAF mw    │      │   .db    │  │
│   │  E2E crypto  │            └──────┬────────┘      └──────────┘  │
│   └──────────────┘                  │                              │
│                              ┌──────▼───────┐                      │
│      Web Crypto API ◀───────▶│  Rust Core   │                      │
│     (X25519 in browser)      │ vortex_chat  │                      │
│                              │ AES·BLAKE3   │                      │
│                              │ Argon2·X25519│                      │
│                              └──────────────┘                      │
└──────────────────────────────────┬─────────────────────────────────┘
                                   │ UDP broadcast :4200
                 ┌─────────────────┼──────────────────┐
                 ▼                 ▼                   ▼
            Node A             Node B              Node C
          (ноутбук)        (Raspberry Pi)        (телефон)
```

### Мультихоп-маршрутизация (A→B→C)

```
Browser A      Node-A (home)      Node-B (relay)     Node-C (target)
    │               │                   │                   │
    │  POST         │                   │                   │
    │  multihop-join│                   │                   │
    │──────────────▶│                   │                   │
    │               │  POST /federated  │                   │
    │               │──────────────────▶│                   │
    │               │                   │  POST /join       │
    │               │                   │──────────────────▶│
    │               │◀──────────────────│◀── { token } ─────│
    │◀── { room } ──│                   │                   │
    │  WS messages  │  WS proxy relay   │  WS proxy relay   │
    │══════════════▶│══════════════════▶│══════════════════▶│
```

**Защита от петель:** каждый пакет несёт `msg_id` (UUID4) + `ttl=7`. Каждый узел хранит кеш `seen_ids` (1000 записей, LRU). Дубли отбрасываются, TTL уменьшается на каждом хопе.

---

## 🔐 E2E шифрование — как это работает

VORTEX реализует **истинное end-to-end шифрование**: сервер в любой момент видит только зашифрованный ciphertext и физически не может прочитать сообщения.

### Схема обмена ключами

```
Регистрация:
  Клиент → генерирует X25519 keypair (Web Crypto API)
  Приватный ключ → localStorage (JWK, никогда не покидает браузер)
  Публичный ключ → сервер (хранит открыто)

Создание комнаты:
  Создатель → генерирует room_key (32 random bytes)
  room_key → ECIES-шифруется под свой собственный pubkey
  Зашифрованный blob → сервер (хранит, но не может расшифровать)

Вступление нового участника:
  1. Сервер уведомляет онлайн-участников: key_request{new_user_pubkey}
  2. Онлайн-участник: ECIES-расшифровывает room_key своим privkey
  3. Re-encrypt: ECIES-шифрует room_key под pubkey нового участника
  4. key_response{re_encrypted_key} → сервер → новому участнику
  5. Новый участник расшифровывает room_key своим privkey → готово

Отправка сообщения:
  plaintext → AES-256-GCM(room_key, nonce=random(12)) → ciphertext
  ciphertext → WebSocket → сервер → broadcast → участники
  Каждый участник: AES-256-GCM-decrypt(room_key) → plaintext
```

### Криптографические примитивы

| Операция | Алгоритм | Реализация |
|---|---|---|
| Асимметричный DH | X25519 (Curve25519) | Rust `x25519-dalek` |
| KDF | HKDF-SHA256 | Rust `hkdf` |
| Симметричное шифрование | AES-256-GCM (AEAD) | Rust `aes-gcm` |
| Хэширование | BLAKE3 | Rust `blake3` |
| Хэширование паролей | Argon2id | Rust `argon2` |
| Сравнение токенов | SHA-256 constant-time | Rust `subtle` |
| Браузерная крипто | Web Crypto API | Нативно в браузере |
| Python fallback | `cryptography.hazmat` | При недоступности Rust |

---

## 📊 Мониторинг качества звонков

VORTEX — единственный мессенджер в сравнении, который показывает реальные метрики качества соединения прямо в интерфейсе звонка.

### Что отображается

**В самом звонке (всегда видно под статусом):**
```
● Задержка: 42 мс
```
Цвет точки меняется автоматически:
- 🟢 Зелёный — RTT < 150 мс, потери < 2%, джиттер < 30 мс
- 🟡 Жёлтый — RTT < 300 мс, потери < 8%, джиттер < 80 мс
- 🔴 Красный — хуже пороговых значений

**При нажатии ⚙ — полная панель статистики:**

| Параметр | Пример | Откуда |
|---|---|---|
| Задержка (RTT) | 42 мс | `candidate-pair.currentRoundTripTime` |
| Джиттер | 8 мс | `inbound-rtp.jitter` |
| Потери пакетов | 0.2 % | Delta `packetsLost / packetsReceived` |
| Входящий поток | 48 kbps | Delta `bytesReceived / dt` |
| Тип соединения | Прямое (LAN) | `local-candidate.candidateType` |
| Качество | Хорошее | Сводная оценка по порогам |

Панель обновляется каждые 2 секунды с точным временем последнего обновления.

### Техническая реализация

```javascript
// RTCPeerConnection.getStats() → delta-расчёт каждые 2 секунды
statsReport.forEach(report => {
    if (report.type === 'candidate-pair' && report.state === 'succeeded')
        rtt = report.currentRoundTripTime * 1000;              // RTT мс

    if (report.type === 'inbound-rtp' && report.kind === 'audio') {
        jitter      = report.jitter * 1000;                    // джиттер мс
        packetsLost = report.packetsLost;
        bytesRecv   = report.bytesReceived;
    }
});

// Потери = delta за последние 2 сек, не накопленное
const lossPercent = (deltaLost / (deltaLost + deltaRecv)) * 100;
const bitrateKbps = (deltaBytes * 8) / dt / 1000;
```

---

## 📡 Транспортный стек

### Приоритет транспортов

VORTEX автоматически выбирает лучший доступный транспорт:

```
Приоритет    Транспорт            Условие использования
─────────────────────────────────────────────────────────────────
4 (лучший)  Direct TCP/WS        Оба узла в одной LAN
3           UDP Hole Punch        Узлы за разными NAT
2           Wi-Fi Direct P2P     Нет точки доступа, устройства рядом
1           BLE                  Wi-Fi недоступен, < 512 байт
0 (fallback) Federation Relay    Все прямые пути недоступны
```

---

### NAT Traversal (STUN + UDP Hole Punching)

**Поддерживаемые типы NAT:**

| Тип NAT | Поддержка | Метод |
|---|---|---|
| Full-cone | ✅ | Hole punch |
| Restricted-cone | ✅ | Hole punch |
| Port-restricted | ✅ | Hole punch |
| Symmetric | ⚠️ | Relay fallback |

**Протокол:**
```
1. Node A: gather_candidates() → host + srflx (через STUN)
2. Node A → POST /api/transport/signal (кандидаты A → Node B)
3. Node B: gather_candidates() → host + srflx
4. Node B → POST /api/transport/signal (кандидаты B → Node A)
5. Одновременно: punch() → 10 попыток × 0.3 сек
6. NAT открывает порт → ACK → прямой UDP туннель
```

**STUN серверы:** `stun.l.google.com:19302`, `stun1.l.google.com:19302`, `stun.cloudflare.com:3478`, `stun.stunprotocol.org:3478`

---

### Wi-Fi Direct (P2P без точки доступа)

| Платформа | Поддержка | Бэкенд |
|---|---|---|
| Linux | ✅ | wpa_supplicant через `wpa_cli` |
| Windows 10+ | ✅ | WinRT `WiFiDirect` API |
| macOS | ⚠️ | Ограниченно |

Режимы: **PBC** (Push Button, без PIN) и **PIN**. Дальность до ~200 м, скорость до 250 Мбит/с.

---

### BLE (Bluetooth Low Energy) fallback

```
MTU:        20–244 байт/пакет → автоматическая фрагментация
Скорость:   ~100–250 kbps
Дальность:  ~10–30 м
Применение: discovery + сообщения < 512 байт
            НЕ используется для файлов и звонков

Service UUID: a1b2c3d4-0000-4e00-8000-56789abcdef0
Платформы:    Windows 10+, Linux (BlueZ 5.43+), macOS
```

---

### Transport Manager API

```
GET  /api/transport/status          — статус всех транспортов
POST /api/transport/signal          — принять ICE кандидаты
POST /api/transport/punch           — инициировать hole punch (async)
POST /api/transport/punch/sync      — hole punch (sync, ждёт результата)
GET  /api/transport/nat/info        — внешний IP:port
POST /api/transport/nat/refresh-stun — обновить STUN
GET  /api/transport/ble/peers       — BLE пиры с RSSI
POST /api/transport/ble/scan        — принудительный BLE-скан
GET  /api/transport/wifi-direct/peers — Wi-Fi Direct пиры
POST /api/transport/wifi-direct/connect — подключиться (PBC/PIN)
POST /api/transport/wifi-direct/create-group — создать P2P группу
```

---

## 📨 Протоколы

### WebSocket сообщения

```
Тип                Направление     Описание
─────────────────────────────────────────────────────────────
message            C→S→C           Зашифрованное сообщение
history            S→C             История последних 50 сообщений
room_key           S→C             ECIES-зашифрованный ключ комнаты
key_request        S→C             Запрос ключа для нового участника
key_response       C→S             Re-encrypted ключ комнаты
invite             S→C             Входящий вызов WebRTC
offer / answer     C→S→C           SDP обмен WebRTC
ice-candidate      C→S→C           ICE кандидаты WebRTC
typing             C→S→C           Индикатор набора текста
ping / pong        C↔S             Keepalive каждые 25 сек
edit / delete      C→S→C           Редактирование/удаление сообщения
file_sending       S→C             Уведомление о входящем файле
```

### Протокол передачи файлов

```
1. Client вычисляет SHA-256 файла до отправки
2. POST /api/files/upload/{room_id} (multipart, XHR с progress)
3. Server сохраняет файл, вычисляет SHA-256 повторно
4. Если хэши не совпадают → 400 Bad Request
5. Server рассылает {type:"file_sending"} через WebSocket
6. Получатель скачивает GET /api/files/download/{file_id}
7. Browser проверяет SHA-256 полученных байт
```

---

## 🔌 API

Интерактивная документация: **`https://localhost:8000/api/docs`**

| Метод | Endpoint | Описание |
|---|---|---|
| `POST` | `/api/authentication/register` | Регистрация |
| `POST` | `/api/authentication/login` | Вход (пароль или X25519 challenge) |
| `GET` | `/api/authentication/me` | Текущий пользователь |
| `GET` | `/api/authentication/csrf-token` | CSRF токен |
| `POST` | `/api/authentication/logout` | Выход |
| `POST` | `/api/rooms` | Создать комнату |
| `GET` | `/api/rooms/my` | Мои комнаты |
| `GET` | `/api/rooms/public` | Публичные комнаты |
| `POST` | `/api/rooms/join/{code}` | Вступить по инвайт-коду |
| `GET` | `/api/rooms/{id}/members` | Участники комнаты |
| `POST` | `/api/files/upload/{room_id}` | Загрузить файл |
| `GET` | `/api/files/download/{file_id}` | Скачать файл |
| `GET` | `/api/files/room/{room_id}` | Список файлов комнаты |
| `GET` | `/api/peers` | Список активных узлов |
| `POST` | `/api/peers/federated-join` | Вступить в комнату другого узла |
| `POST` | `/api/peers/multihop-join` | Вступить через промежуточный узел |
| `POST` | `/api/federation/guest-login` | Гостевой вход (только RFC 1918) |
| `WS` | `/ws/{room_id}` | WebSocket чата (E2E) |
| `WS` | `/ws/signal/{room_id}` | WebRTC сигнализация |
| `WS` | `/ws/fed/{virtual_id}` | Федеративный прокси WebSocket |

---

## 🛡 Безопасность и модель угроз

### Реализованные механизмы

| Механизм | Реализация |
|---|---|
| **Аутентификация** | JWT HS256 + opaque refresh-токены, SHA-256 хэш в БД |
| **CSRF** | Double Submit Cookie — `HttpOnly` cookie + заголовок `X-CSRF-Token` |
| **Пароли** | Argon2id (Rust) — GPU/ASIC-стойкое хэширование с солью |
| **E2E шифрование** | X25519 DH → HKDF-SHA256 → AES-256-GCM, уникальный ключ на комнату |
| **Ключи комнат** | ECIES re-encryption при каждом новом участнике |
| **Целостность файлов** | SHA-256 на сервере при загрузке и в браузере при скачивании |
| **WAF** | Блокировка SQLi, XSS, path traversal, null bytes, command injection |
| **Rate limiting** | 120 req/min на IP, автоблокировка на 1 час |
| **HTTP заголовки** | CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| **IP валидация** | RFC 1918 whitelist для federation endpoints |
| **Constant-time** | `subtle::ConstantTimeEq` (Rust) для сравнения токенов |

### Матрица угроз

| Угроза | Вектор | Защита |
|---|---|---|
| Перехват трафика (MITM) | Сниффинг LAN | HTTPS TLS 1.2+ + E2E |
| Чтение сообщений сервером | Компрометация узла | Сервер видит только ciphertext |
| Replay-атака | Повтор запроса | JWT exp + одноразовый challenge |
| SQL-инъекция | Поле ввода | WAF + параметризованные запросы |
| XSS | display_name, сообщение | CSP + `esc()` для всех данных |
| CSRF | JS с чужого домена | Double Submit Cookie |
| Brute-force пароля | `/login` | Rate limiting + Argon2id (slow) |
| Path traversal | `/download` | WAF + UUID-based file IDs |
| Спуфинг пира | Поддельный узел | HTTPS + IP whitelist RFC 1918 |
| Flood ретранслятора | Пакетная бомба | WAF rate limit + TTL на пакетах |
| Тайминг-атака | Сравнение хэшей | `subtle::ConstantTimeEq` |

### Известные ограничения

```
⚠️  Приватный X25519 ключ хранится в localStorage
    (стандартная браузерная модель, как в Signal Web)
⚠️  Доверие к своему узлу — пользователь доверяет узлу,
    на котором зарегистрирован (как Matrix/XMPP self-hosted)
```

---

## 🔁 Надёжность

### Reconnect WebSocket

При разрыве клиент переподключается автоматически через 3 секунды:

```javascript
S.ws.onclose = () => {
    if (S.currentRoom?.id === roomId)
        setTimeout(() => connectWS(roomId), 3_000);
};
```

### Очередь сообщений (без потерь при временном разрыве)

```javascript
// Promise-chain: строгая последовательность обработки
S.ws.onmessage = e => {
    _msgQueue = _msgQueue
        .then(() => handleWsMessage(data))
        .catch(err => console.error('WS msg error:', err));
};
```

### Ping / Keepalive

Клиент отправляет `{action:"ping"}` каждые 25 секунд. Сервер отвечает `{type:"pong"}`. Нет pong — соединение мёртвое, переустанавливается.

### Дедупликация и TTL

```
Каждый пакет: { msg_id: UUID4, ttl: 7, payload: ... }
На каждом узле:
  if msg_id in seen_cache → drop
  else: seen_cache.add(msg_id); ttl -= 1; if ttl > 0 → forward
Кеш seen_ids: 1000 записей, LRU-вытеснение
```

### Деградация при недоступности Rust

```
vortex_chat (Rust) → доступен?
  ✓ → AES-GCM, Argon2id, BLAKE3, X25519 (нативная скорость)
  ✗ → Python fallback: cryptography.hazmat + PBKDF2-SHA256
```

---

## 📱 PWA — установка как приложение

VORTEX является полноценным **Progressive Web App** и устанавливается как нативное приложение на любой платформе — без магазина приложений, без APK, без .exe.

### Поддержка платформ

| Платформа | Браузер | Установка | Офлайн | Уведомления |
|---|---|---|---|---|
| Windows 10/11 | Chrome, Edge | ✅ кнопка в адресной строке | ✅ | ✅ |
| macOS | Chrome, Edge | ✅ кнопка в адресной строке | ✅ | ✅ |
| Linux | Chrome, Chromium | ✅ кнопка в адресной строке | ✅ | ✅ |
| Android | Chrome | ✅ баннер «Добавить на экран» | ✅ | ✅ |
| iOS 16.4+ | Safari | ✅ «Поделиться → На экран» | ✅ | ⚠️ ограничено |
| Raspberry Pi | Chromium | ✅ | ✅ | ✅ |

### Что получаешь после установки

- **Иконка на рабочем столе / экране телефона** — запуск без браузера
- **Отдельное окно** (без адресной строки, как нативное приложение)
- **Работает офлайн** — UI загружается из кэша, переподключается при появлении узла
- **Push-уведомления** о новых сообщениях когда окно свёрнуто
- **Shortcuts** — правая кнопка по иконке → «Новая комната», «Вступить по коду»
- **Protocol handler** `web+vortex://` — кликабельные ссылки-инвайты
- **Баннер обновления** — при новой версии предлагает перезагрузить

### Установка PWA-компонентов

```bash
# Генерация иконок (нужна один раз)
pip install cairosvg
python generate_icons.py

# Копируем файлы в проект
cp manifest.json         Vortex/static/
cp service-worker.js     Vortex/static/js/
cp pwa.js                Vortex/static/js/
```

Детальная инструкция по подключению в существующий код — в файле [`PWA_INTEGRATION.md`](PWA_INTEGRATION.md).

### Стратегии кэширования (service-worker.js)

```
Тип ресурса          Стратегия          Поведение
───────────────────────────────────────────────────────────────────
static/js,css,icons  Cache-First        Мгновенный старт, офлайн
/api/* запросы       Network-First      Свежие данные, fallback в кэш
HTML страница        Network-First      При офлайн — заглушка с инструкцией
WebSocket            Не перехватывается SW не может перехватить WS
```

Офлайн-заглушка показывает команду `python run.py` и кнопку «Повторить подключение».

### Структура PWA-файлов

```
Vortex/
├── static/
│   ├── manifest.json              ← Web App Manifest
│   ├── js/
│   │   ├── service-worker.js      ← Service Worker (кэш, офлайн, push)
│   │   └── pwa.js                 ← PWA модуль (регистрация, промпт, shortcuts)
│   └── icons/
│       ├── icon-72.png
│       ├── icon-96.png
│       ├── icon-128.png
│       ├── icon-144.png
│       ├── icon-152.png
│       ├── icon-192.png            ← основная (maskable — Android)
│       ├── icon-384.png
│       ├── icon-512.png            ← splash screen (maskable)
│       └── favicon.png             ← 32x32 для браузерной вкладки
└── generate_icons.py              ← генератор иконок (cairosvg / Pillow)
```

---

## 📈 Метрики и производительность

### Криптографическая производительность (Rust core, Apple M1 Pro)

| Операция | Средняя | p99 |
|---|---|---|
| AES-256-GCM encrypt (256 байт) | < 0.05 мс | < 0.2 мс |
| AES-256-GCM encrypt (1 МБ) | < 2 мс | < 5 мс |
| SHA-256 (10 МБ) | < 20 мс | — |
| ECIES полный цикл | < 5 мс | < 15 мс |
| Argon2id hash | ~100 мс | — |
| X25519 DH | < 0.1 мс | — |

### Rust vs Python fallback

| Операция | Rust | Python | Ускорение |
|---|---|---|---|
| AES-256-GCM (1 МБ) | ~2 мс | ~18 мс | **9×** |
| BLAKE3 (1 МБ) | ~0.3 мс | ~8 мс (SHA-256) | **27×** |
| X25519 DH | ~0.1 мс | ~1.2 мс | **12×** |

### WebRTC по типу соединения

| Параметр | LAN (direct) | NAT (STUN) | Relay |
|---|---|---|---|
| RTT | < 1 мс | 20–80 мс | 80–200 мс |
| Jitter | < 5 мс | 5–30 мс | 10–50 мс |
| Потери пакетов | < 0.1 % | < 1 % | < 2 % |

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все Python тесты
pytest

# С подробным выводом
pytest -v --tb=short

# По группам
pytest -m crypto
pytest -m security
pytest -m integration

# Rust тесты
cd rust_utils && cargo test -- --nocapture
```

### Покрытие

| Область | Python | Rust |
|---|---|---|
| AES-256-GCM | 7 тестов | 5 тестов |
| SHA-256 / BLAKE3 | 5 тестов | 2 теста |
| X25519 / ECIES | 4 теста | 3 теста |
| Argon2id | 2 теста | нативно |
| Аутентификация | 11 тестов | — |
| Комнаты | 7 тестов | — |
| Файлы | 5 тестов | — |
| Надёжность | 5 тестов (multihop, TTL, dedup) | — |
| Безопасность | 10 тестов (SQLi, XSS, CSRF) | — |
| Метрики / latency | 4 бенчмарка | 1 бенчмарк |
| UDP discovery | — | 15 тестов |
| **Итого** | **60+** | **23** |

---

## 📁 Структура проекта

```
Vortex/
├── run.py                        ← точка входа
├── requirements.txt
├── pytest.ini
├── .env                          ← конфигурация (создаётся wizard-ом)
├── README.md
├── ARCHITECTURE.md
│
├── node_setup/                   ← мастер первоначальной настройки
│   ├── wizard.py                 ← FastAPI сервер wizard-а (порт 7979)
│   ├── ssl_manager.py            ← self-signed / mkcert / certbot
│   └── static/js/setup.js
│
├── app/
│   ├── main.py                   ← FastAPI app + middleware stack
│   ├── config.py                 ← Config из .env
│   ├── models.py                 ← SQLAlchemy модели (WAL mode)
│   ├── authentication/auth.py    ← JWT, X25519 challenge-response
│   ├── chats/
│   │   ├── chat.py               ← WebSocket E2E relay, WebRTC signaling
│   │   └── rooms.py              ← CRUD комнат, key-bundle, invite-codes
│   ├── peer/
│   │   ├── peer_registry.py      ← UDP discovery, federated-join, multihop
│   │   ├── connection_manager.py ← ConnectionManager, broadcast_to_room()
│   │   └── federation.py         ← FederationRelayManager, virtual rooms
│   ├── security/
│   │   ├── crypto.py             ← Rust/Python fallback крипто-утилиты
│   │   ├── auth_jwt.py           ← JWT + refresh tokens
│   │   ├── waf.py                ← WAFEngine + WAFMiddleware
│   │   └── middleware.py         ← SecurityHeaders, CSRF, TokenRefresh
│   ├── transport/
│   │   ├── transport_manager.py  ← TransportManager, приоритеты
│   │   ├── nat_traversal.py      ← StunClient, UdpHolePuncher
│   │   ├── ble_transport.py      ← BleTransportManager, BleFragmenter
│   │   ├── wifi_direct.py        ← Linux/Windows Wi-Fi Direct
│   │   └── routes.py             ← /api/transport/* endpoints
│   └── tests/
│       ├── tests.py              ← 60+ pytest тестов
│       └── conftest.py           ← фикстуры, SyncASGIClient
│
├── rust_utils/                   ← Rust криптоядро (PyO3 / maturin)
│   └── src/
│       ├── lib.rs                ← PyO3 bindings
│       ├── messages/crypt.rs     ← AES-256-GCM
│       ├── messages/hash.rs      ← BLAKE3 + keygen
│       ├── auth/passwords.rs     ← Argon2id
│       ├── auth/tokens.rs        ← SHA-256 constant-time
│       ├── crypto/handshake.rs   ← X25519 + HKDF-SHA256
│       └── udp_broadcast/discovery.rs ← UDP broadcast (15 тестов)
│
├── generate_icons.py             ← генератор PWA иконок (cairosvg / Pillow)
│
└── static/
    ├── manifest.json             ← PWA Web App Manifest
    ├── icons/                    ← иконки 72/96/128/144/152/192/384/512 + favicon
    └── js/                       ← фронтенд (vanilla JS ESM)
        ├── main.js               ← AppState, bootApp()
        ├── auth.js               ← X25519 keypair, JWT
        ├── crypto.js             ← ECIES (Web Crypto API)
        ├── rooms.js              ← комнаты, федерация, multihop
        ├── webrtc.js             ← WebRTC, getStats(), RTT мониторинг
        ├── pwa.js                ← PWA: SW регистрация, промпт установки, shortcuts
        ├── service-worker.js     ← Service Worker: кэш, офлайн-заглушка, push
        ├── ui.js, utils.js, peers.js
        ├── photo_editor.js       ← canvas-редактор фото
        ├── voice_recorder.js     ← голосовые, live waveform
        └── chat/
            ├── chat.js           ← WebSocket + E2E шифрование
            ├── messages.js       ← рендеринг сообщений
            ├── file-upload.js    ← XHR upload с прогрессом
            └── liquid-glass.js   ← glassmorphism эффекты
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