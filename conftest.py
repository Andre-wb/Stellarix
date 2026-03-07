"""
conftest.py — глобальные фикстуры и настройки pytest для VORTEX.
Положи в корень проекта рядом с pytest.ini: /Vortex/conftest.py
"""

import asyncio
import os
import secrets
import string
import sys

# ---------------------------------------------------------------------------
# Добавляем корень проекта в sys.path чтобы импорт app.* работал
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Устанавливаем переменные окружения ДО импорта приложения
# ---------------------------------------------------------------------------
os.environ.setdefault('TESTING',                 'true')
os.environ.setdefault('DB_PATH', 'file::memory:?cache=shared')
os.environ.setdefault('JWT_SECRET',              'test_secret_key_minimum_32_chars_long_1234')
os.environ.setdefault('CSRF_SECRET',             'test_csrf_secret_minimum_32_chars_1234567')
os.environ.setdefault('NODE_INITIALIZED',        'true')
os.environ.setdefault('DEVICE_NAME',             'TestNode')
os.environ.setdefault('PORT',                    '8001')
os.environ.setdefault('HOST',                    '127.0.0.1')
os.environ.setdefault('UDP_PORT',                '4201')
os.environ.setdefault('MAX_FILE_MB',             '100')
os.environ.setdefault('WAF_RATE_LIMIT_REQUESTS', '9999')

import httpx
import pytest

# ---------------------------------------------------------------------------
# Импорт приложения (после установки env)
# ---------------------------------------------------------------------------
from app.main import app  # noqa: E402


# ===========================================================================
# Обёртка над httpx.AsyncClient + ASGITransport
# ===========================================================================

class SyncASGIClient:
    """
    Синхронная обёртка над httpx.AsyncClient для тестирования ASGI-приложений.

    КРИТИЧНО: startup, все HTTP-запросы и shutdown должны выполняться
    в ОДНОМ event loop. SQLite :memory: создаёт таблицы в соединении,
    привязанном к loop-у startup. Если запросы идут в другом loop-е —
    таблицы не видны ("no such table") или соединение "detached".

    Исправление: loop создаётся ЗДЕСЬ и передаётся в startup/shutdown снаружи
    через фикстуру client, которая использует именно этот loop для всего.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self._transport = httpx.ASGITransport(app=app)
        self._base_url  = 'http://testserver'
        self._cookies   = httpx.Cookies()
        self._own_loop  = loop is None
        self._loop      = loop if loop is not None else asyncio.new_event_loop()

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def _do() -> httpx.Response:
            async with httpx.AsyncClient(
                    transport=self._transport,
                    base_url=self._base_url,
                    cookies=self._cookies,
                    follow_redirects=True,
            ) as client:
                resp = await getattr(client, method)(url, **kwargs)
                self._cookies.update(resp.cookies)
                return resp
        return self._loop.run_until_complete(_do())

    def get(self, url: str, **kwargs)    -> httpx.Response: return self._send('get',    url, **kwargs)
    def post(self, url: str, **kwargs)   -> httpx.Response: return self._send('post',   url, **kwargs)
    def put(self, url: str, **kwargs)    -> httpx.Response: return self._send('put',    url, **kwargs)
    def delete(self, url: str, **kwargs) -> httpx.Response: return self._send('delete', url, **kwargs)

    def close(self):
        if self._own_loop:
            try:
                self._loop.close()
            except Exception:
                pass

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


# ===========================================================================
# SESSION-SCOPE: один клиент на всю сессию тестов
# ===========================================================================

@pytest.fixture(scope='session')
def client() -> SyncASGIClient:
    """
    Единственный SyncASGIClient на всю сессию.

    ВАЖНО: startup() запускается в ТОМ ЖЕ loop, что и все последующие
    HTTP-запросы. SQLite :memory: привязана к конкретному соединению/loop —
    если startup и запросы используют разные loop-ы, таблицы окажутся
    в разных in-memory базах и будут невидимы ("no such table: users").

    Старый баг был здесь:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(app.router.startup())  # loop A — создаёт таблицы
        c = SyncASGIClient()  # loop B (новый!) — таблиц не видит
    """
    loop = asyncio.new_event_loop()
    c = SyncASGIClient(loop=loop)           # ← клиент использует loop
    loop.run_until_complete(app.router.startup())  # ← startup в том же loop

    yield c

    loop.run_until_complete(app.router.shutdown())
    c.close()
    loop.close()


# ===========================================================================
# Вспомогательные утилиты (доступны из всех тестов через импорт conftest)
# ===========================================================================

def random_str(n: int = 10) -> str:
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def random_digits(n: int = 7) -> str:
    """Строка только из цифр — для генерации телефонных номеров."""
    return ''.join(secrets.choice(string.digits) for _ in range(n))


def make_user(client: SyncASGIClient, suffix: str | None = None) -> dict:
    """
    Регистрирует пользователя и возвращает его данные + заголовки.
    Телефон строится только из цифр, чтобы пройти валидацию Pydantic.
    """
    tag = suffix or random_str()
    payload = {
        'username':          f'user_{tag}',
        'password':          'StrongPass99x',
        'display_name':      f'Test {tag}',
        'phone':             f'+7900{random_digits(7)}',
        'avatar_emoji':      '🤖',
        'x25519_public_key': secrets.token_hex(32),
    }
    r = client.post('/api/authentication/register', json=payload)
    assert r.status_code == 201, f'register failed ({r.status_code}): {r.text}'
    csrf = client.get('/api/authentication/csrf-token').json().get('csrf_token', '')
    return {
        'username':   payload['username'],
        'password':   payload['password'],
        'data':       r.json(),
        'headers':    {'X-CSRF-Token': csrf},
        'x25519_pub': payload['x25519_public_key'],
    }


def login_user(client: SyncASGIClient, username: str, password: str) -> dict:
    """Логинит пользователя, возвращает словарь с заголовками."""
    csrf = client.get('/api/authentication/csrf-token').json().get('csrf_token', '')
    r = client.post('/api/authentication/login', json={
        'phone_or_username': username,
        'password':          password,
    }, headers={'X-CSRF-Token': csrf})
    assert r.status_code == 200, f'login failed ({r.status_code}): {r.text}'
    return {'X-CSRF-Token': csrf}


# ===========================================================================
# FUNCTION-SCOPE фикстуры
# ===========================================================================

@pytest.fixture
def fresh_user(client: SyncASGIClient) -> dict:
    """Новый пользователь (только зарегистрирован, не залогинен)."""
    return make_user(client)


@pytest.fixture
def logged_user(client: SyncASGIClient, fresh_user: dict) -> dict:
    """Зарегистрированный и залогиненный пользователь."""
    headers = login_user(client, fresh_user['username'], fresh_user['password'])
    fresh_user['headers'] = headers
    return fresh_user


@pytest.fixture
def room(client: SyncASGIClient, logged_user: dict) -> dict:
    """Тестовая комната, созданная logged_user."""
    r = client.post('/api/rooms', json={
        'name':          f'room_{random_str()}',
        'is_public':     True,
        'encrypted_key': secrets.token_hex(60),
        'ephemeral_pub': secrets.token_hex(32),
    }, headers=logged_user['headers'])
    assert r.status_code in (200, 201), f'create room failed: {r.text}'
    return r.json()


@pytest.fixture
def two_users(client: SyncASGIClient):
    """Два залогиненных пользователя (для тестов взаимодействия)."""
    u1 = make_user(client, suffix=f'a{random_str(6)}')
    u2 = make_user(client, suffix=f'b{random_str(6)}')
    h1 = login_user(client, u1['username'], u1['password'])
    h2 = login_user(client, u2['username'], u2['password'])
    u1['headers'] = h1
    u2['headers'] = h2
    return u1, u2


# ===========================================================================
# Хук: выводим метрики после тестов
# ===========================================================================

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Добавляем секцию метрик в финальный отчёт."""
    passed  = len(terminalreporter.stats.get('passed',  []))
    failed  = len(terminalreporter.stats.get('failed',  []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    total   = passed + failed + skipped

    terminalreporter.write_sep('=', 'VORTEX Test Summary')
    terminalreporter.write_line(f'  Total:   {total}')
    terminalreporter.write_line(f'  Passed:  {passed}  ✅')
    if failed:
        terminalreporter.write_line(f'  Failed:  {failed}  ❌')
    if skipped:
        terminalreporter.write_line(f'  Skipped: {skipped}  ⏭')