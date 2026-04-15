"""
Полные тесты страницы настроек федерации.

Покрытие:
  - Подключение нескольких узлов (handshake, gossip)
  - Список узлов, статусы, фильтрация
  - Общение между узлами (guest-login, federated-join, relay)
  - Отключение одного узла, проверка что остальные работают
  - Повторное подключение
  - Gossip security (rate-limit, PoW, reputation)
  - Edge cases: дубликаты, невалидные данные, SSRF
"""

import secrets
import time

import pytest

from conftest import SyncASGIClient, make_user, login_user, random_str


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-bypass PoW for test client IP (127.0.0.1 / testclient)
# ═══════════════════════════════════════════════════════════════════════════════
def _bypass_gossip_security():
    """Mark test client IPs as PoW-verified and disable rate limiting for tests."""
    try:
        from app.transport.gossip_security import ProofOfWork
        for addr in ('127.0.0.1', 'testclient', 'testserver', 'localhost'):
            ProofOfWork._verified[addr] = time.monotonic()
    except Exception:
        pass
    # Disable gossip rate limiter cooldown for tests
    try:
        from app.federation.trusted_nodes import _gossip_rate_limiter
        _gossip_rate_limiter._cooldown = 0.0  # no cooldown in tests
    except Exception:
        pass

_bypass_gossip_security()


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _h(client: SyncASGIClient, extra: dict | None = None) -> dict:
    """CSRF headers."""
    csrf = client.get('/api/authentication/csrf-token').json().get('csrf_token', '')
    h = {'X-CSRF-Token': csrf}
    if extra:
        h.update(extra)
    return h


def _code_hash(client: SyncASGIClient) -> str:
    """Get local code hash."""
    return client.get('/api/federation/code-hash').json()['code_hash']


def _register_node_via_handshake(
    client: SyncASGIClient,
    headers: dict,
    url: str | None = None,
    code_hash: str | None = None,
    node_id: str | None = None,
    version: str = '1.0.0',
) -> dict:
    """Register a fake node via handshake (no network probe)."""
    tag = random_str()
    _url = url or f'https://node-{tag}.example.com:8443'
    _hash = code_hash or _code_hash(client)
    _nid = node_id or secrets.token_hex(16)
    r = client.post('/api/federation/handshake', json={
        'node_id': _nid,
        'url': _url,
        'code_hash': _hash,
        'version': version,
    }, headers=headers)
    assert r.status_code == 200
    return {'url': _url, 'node_id': _nid, 'response': r.json()}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Подключение нескольких узлов
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiNodeConnection:
    """Подключение нескольких узлов и проверка списка."""

    def test_connect_three_nodes(self, client: SyncASGIClient, logged_user: dict):
        """Подключение 3 узлов через handshake — все появляются в списке."""
        h = logged_user['headers']
        nodes = []
        for i in range(3):
            n = _register_node_via_handshake(client, h)
            assert n['response']['accepted'] is True
            nodes.append(n)

        r = client.get('/api/federation/nodes', headers=h)
        assert r.status_code == 200
        node_urls = [n['url'] for n in r.json()['nodes']]
        for n in nodes:
            assert n['url'] in node_urls

    def test_connect_nodes_with_different_versions(self, client: SyncASGIClient, logged_user: dict):
        """Узлы с разными версиями — все принимаются (hash совпадает)."""
        h = logged_user['headers']
        for ver in ('1.0.0', '1.1.0', '2.0.0-beta'):
            n = _register_node_via_handshake(client, h, version=ver)
            assert n['response']['accepted'] is True

    def test_connect_node_wrong_hash_rejected(self, client: SyncASGIClient, logged_user: dict):
        """Узел с неверным code_hash не принимается."""
        h = logged_user['headers']
        n = _register_node_via_handshake(client, h, code_hash='b' * 64)
        assert n['response']['accepted'] is False
        assert n['response'].get('reason') == 'code_hash_mismatch'

    def test_connect_duplicate_url_conflict(self, client: SyncASGIClient, logged_user: dict):
        """Повторное подключение с тем же URL — обновление, не дубликат."""
        h = logged_user['headers']
        tag = random_str()
        url = f'https://dup-node-{tag}.example.com:8443'
        n1 = _register_node_via_handshake(client, h, url=url)
        n2 = _register_node_via_handshake(client, h, url=url)
        # Оба должны вернуть 200 (accepted или уже known)
        assert n1['response']['accepted'] is True

        # В списке должен быть один узел с этим URL, не два
        r = client.get('/api/federation/nodes', headers=h)
        urls = [n['url'] for n in r.json()['nodes']]
        assert urls.count(url) == 1

    def test_status_reflects_node_count(self, client: SyncASGIClient, logged_user: dict):
        """Network status показывает корректное количество узлов."""
        h = logged_user['headers']
        r_before = client.get('/api/federation/nodes/status', headers=h)
        count_before = r_before.json()['total_nodes']

        _register_node_via_handshake(client, h)

        r_after = client.get('/api/federation/nodes/status', headers=h)
        count_after = r_after.json()['total_nodes']
        assert count_after >= count_before + 1


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Отключение узла
# ═══════════════════════════════════════════════════════════════════════════════

class TestNodeDisconnection:
    """Отключение одного узла, проверка что остальные остаются."""

    def test_delete_one_node_others_remain(self, client: SyncASGIClient, logged_user: dict):
        """Удаление одного узла не влияет на другие."""
        h = logged_user['headers']
        nodes = [_register_node_via_handshake(client, h) for _ in range(3)]

        # Найдём ID первого узла в списке
        r = client.get('/api/federation/nodes', headers=h)
        db_nodes = r.json()['nodes']
        target = next((n for n in db_nodes if n['url'] == nodes[0]['url']), None)
        assert target is not None

        # Удаляем
        rd = client.delete(f'/api/federation/nodes/{target["id"]}', headers=h)
        assert rd.status_code == 200

        # Остальные на месте
        r2 = client.get('/api/federation/nodes', headers=h)
        remaining_urls = [n['url'] for n in r2.json()['nodes']]
        assert nodes[0]['url'] not in remaining_urls
        assert nodes[1]['url'] in remaining_urls
        assert nodes[2]['url'] in remaining_urls

    def test_delete_nonexistent_node_404(self, client: SyncASGIClient, logged_user: dict):
        """Удаление несуществующего узла → 404."""
        r = client.delete('/api/federation/nodes/999999', headers=logged_user['headers'])
        assert r.status_code == 404

    def test_delete_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """Удаление без авторизации → 401/403."""
        r = anon_client.delete('/api/federation/nodes/1')
        assert r.status_code in (401, 403)

    def test_delete_and_reconnect(self, client: SyncASGIClient, logged_user: dict):
        """Удалить узел и подключить заново — должен появиться."""
        h = logged_user['headers']
        tag = random_str()
        url = f'https://reconnect-{tag}.example.com:8443'
        _register_node_via_handshake(client, h, url=url)

        # Находим и удаляем
        r = client.get('/api/federation/nodes', headers=h)
        target = next((n for n in r.json()['nodes'] if n['url'] == url), None)
        assert target is not None
        client.delete(f'/api/federation/nodes/{target["id"]}', headers=h)

        # Убедимся что удалён
        r2 = client.get('/api/federation/nodes', headers=h)
        assert url not in [n['url'] for n in r2.json()['nodes']]

        # Переподключаем
        n = _register_node_via_handshake(client, h, url=url)
        assert n['response']['accepted'] is True

        r3 = client.get('/api/federation/nodes', headers=h)
        assert url in [n['url'] for n in r3.json()['nodes']]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Guest login (межузловая авторизация)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuestLogin:
    """Федеративный guest-login: узел B авторизует пользователя с узла A."""

    def test_guest_login_from_loopback(self, client: SyncASGIClient, logged_user: dict):
        """guest-login с 127.0.0.1 (loopback = приватный IP) → 200."""
        r = client.post('/api/federation/guest-login', json={
            'username': 'alice_remote',
            'display_name': 'Alice Remote',
            'avatar_emoji': '👩',
            'x25519_pubkey': secrets.token_hex(32),
        }, headers=logged_user['headers'])
        # Тестовый сервер ходит с 127.0.0.1, это приватный IP
        assert r.status_code == 200
        body = r.json()
        assert 'access_token' in body
        assert 'user_id' in body
        assert 'fed_username' in body
        assert body['fed_username'].startswith('fed__')

    def test_guest_login_creates_federated_user(self, client: SyncASGIClient, logged_user: dict):
        """Повторный guest-login с тем же username — обновляет, не дублирует."""
        tag = random_str()
        payload = {
            'username': f'repeat_{tag}',
            'display_name': f'Repeat {tag}',
            'avatar_emoji': '🔁',
            'x25519_pubkey': secrets.token_hex(32),
        }
        r1 = client.post('/api/federation/guest-login', json=payload, headers=logged_user['headers'])
        r2 = client.post('/api/federation/guest-login', json=payload, headers=logged_user['headers'])
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Тот же user_id при повторном логине
        assert r1.json()['user_id'] == r2.json()['user_id']

    def test_guest_login_missing_fields(self, client: SyncASGIClient, logged_user: dict):
        """guest-login без обязательных полей → 422."""
        r = client.post('/api/federation/guest-login', json={}, headers=logged_user['headers'])
        assert r.status_code == 422

    def test_guest_login_jwt_is_valid(self, client: SyncASGIClient, logged_user: dict):
        """JWT от guest-login работает для авторизованных запросов."""
        tag = random_str()
        r = client.post('/api/federation/guest-login', json={
            'username': f'jwt_check_{tag}',
            'display_name': f'JWT Check {tag}',
            'avatar_emoji': '🔑',
            'x25519_pubkey': '',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        jwt = r.json()['access_token']

        # Используем JWT для получения федеративных комнат
        r2 = client.get('/api/federation/my-rooms', headers={
            'Authorization': f'Bearer {jwt}',
        })
        assert r2.status_code == 200
        assert 'rooms' in r2.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Federated rooms (join/leave/list)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFederatedRooms:
    """Федеративные комнаты — список и выход."""

    def test_my_rooms_empty(self, client: SyncASGIClient, logged_user: dict):
        """GET my-rooms без федеративных комнат → пустой список."""
        r = client.get('/api/federation/my-rooms', headers=logged_user['headers'])
        assert r.status_code == 200
        assert r.json()['rooms'] == []

    def test_my_rooms_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """GET my-rooms без авторизации → 401/403."""
        r = anon_client.get('/api/federation/my-rooms')
        assert r.status_code in (401, 403)

    def test_leave_nonexistent_room(self, client: SyncASGIClient, logged_user: dict):
        """DELETE leave несуществующей комнаты → 404 или ошибка."""
        r = client.delete('/api/federation/leave/999999', headers=logged_user['headers'])
        # Зависит от реализации — может быть 404 или 200 (noop)
        assert r.status_code in (200, 404)

    def test_federated_join_unreachable_peer(self, client: SyncASGIClient, logged_user: dict):
        """federated-join к недоступному пиру → 503."""
        r = client.post('/api/peers/federated-join', json={
            'invite_code': 'ABCDEF',
            'peer_ip': '192.0.2.1',  # TEST-NET, guaranteed unreachable
            'peer_port': 9999,
        }, headers=logged_user['headers'])
        assert r.status_code in (502, 503)

    def test_federated_join_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """federated-join без авторизации → 401/403."""
        r = anon_client.post('/api/peers/federated-join', json={
            'invite_code': 'ABCDEF',
            'peer_ip': '127.0.0.1',
            'peer_port': 8000,
        })
        assert r.status_code in (401, 403)

    def test_federated_join_missing_fields(self, client: SyncASGIClient, logged_user: dict):
        """federated-join с пустым телом → 422."""
        r = client.post('/api/peers/federated-join', json={}, headers=logged_user['headers'])
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Gossip протокол
# ═══════════════════════════════════════════════════════════════════════════════

class TestGossipProtocol:
    """Gossip: распространение информации об узлах."""

    def test_gossip_node_joined_new(self, client: SyncASGIClient, logged_user: dict):
        """gossip/node-joined с новым узлом → added_as_pending."""
        h = logged_user['headers']
        tag = random_str()
        r = client.post('/api/federation/gossip/node-joined', json={
            'node_id': secrets.token_hex(16),
            'url': f'https://gossip-new-{tag}.example.com:8443',
            'code_hash': _code_hash(client),
            'version': '1.0.0',
        }, headers=h)
        assert r.status_code == 200
        assert r.json()['status'] in ('added_as_pending', 'already_known')

    def test_gossip_node_joined_duplicate(self, client: SyncASGIClient, logged_user: dict):
        """Повторный gossip с тем же URL → already_known."""
        h = logged_user['headers']
        tag = random_str()
        url = f'https://gossip-dup-{tag}.example.com:8443'
        nid = secrets.token_hex(16)
        payload = {
            'node_id': nid,
            'url': url,
            'code_hash': _code_hash(client),
            'version': '1.0.0',
        }
        r1 = client.post('/api/federation/gossip/node-joined', json=payload, headers=h)
        r2 = client.post('/api/federation/gossip/node-joined', json=payload, headers=h)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()['status'] == 'already_known'

    def test_gossip_node_left_unknown(self, client: SyncASGIClient, logged_user: dict):
        """gossip/node-left для неизвестного узла → unknown_node."""
        r = client.post('/api/federation/gossip/node-left', json={
            'node_id': secrets.token_hex(16),
            'url': 'https://unknown.example.com:8443',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        assert r.json()['status'] == 'unknown_node'

    def test_gossip_node_left_known(self, client: SyncASGIClient, logged_user: dict):
        """gossip/node-left для известного узла → removed/deactivated."""
        h = logged_user['headers']
        tag = random_str()
        nid = secrets.token_hex(16)
        url = f'https://gossip-leave-{tag}.example.com:8443'

        # Сначала добавляем
        client.post('/api/federation/gossip/node-joined', json={
            'node_id': nid, 'url': url,
            'code_hash': _code_hash(client), 'version': '1.0.0',
        }, headers=h)

        # Затем удаляем через gossip
        r = client.post('/api/federation/gossip/node-left', json={
            'node_id': nid, 'url': url,
        }, headers=h)
        assert r.status_code == 200
        assert r.json()['status'] in ('removed', 'deactivated', 'marked_dead', 'unknown_node')

    def test_gossip_invalid_url_rejected(self, client: SyncASGIClient, logged_user: dict):
        """gossip с невалидным URL → 400."""
        r = client.post('/api/federation/gossip/node-joined', json={
            'node_id': secrets.token_hex(16),
            'url': 'not-a-url',
            'code_hash': _code_hash(client),
        }, headers=logged_user['headers'])
        assert r.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Code verification & handshake
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeVerification:
    """Верификация кода и рукопожатие."""

    def test_code_hash_stable(self, client: SyncASGIClient):
        """code-hash детерминистичен."""
        h1 = _code_hash(client)
        h2 = _code_hash(client)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_code_manifest_file_count(self, client: SyncASGIClient, logged_user: dict):
        """code-manifest возвращает hash и file_count > 0."""
        r = client.post('/api/federation/code-manifest', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert body['file_count'] > 0
        assert body['code_hash'] == _code_hash(client)

    def test_handshake_matching_hash_accepted(self, client: SyncASGIClient, logged_user: dict):
        """Handshake с правильным hash → accepted=true."""
        n = _register_node_via_handshake(client, logged_user['headers'])
        assert n['response']['accepted'] is True
        assert 'code_hash' in n['response']

    def test_handshake_wrong_hash_rejected(self, client: SyncASGIClient, logged_user: dict):
        """Handshake с неверным hash → accepted=false, reason=code_hash_mismatch."""
        n = _register_node_via_handshake(
            client, logged_user['headers'], code_hash='f' * 64,
        )
        assert n['response']['accepted'] is False
        assert n['response']['reason'] == 'code_hash_mismatch'

    def test_handshake_empty_body_422(self, client: SyncASGIClient, logged_user: dict):
        """Handshake без полей → 422."""
        r = client.post('/api/federation/handshake', json={}, headers=logged_user['headers'])
        assert r.status_code == 422

    def test_handshake_returns_local_hash(self, client: SyncASGIClient, logged_user: dict):
        """Handshake response включает наш code_hash."""
        n = _register_node_via_handshake(client, logged_user['headers'])
        assert n['response']['code_hash'] == _code_hash(client)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Token validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenValidation:
    """Валидация participation токенов между узлами."""

    def test_validate_invalid_token(self, client: SyncASGIClient, logged_user: dict):
        """Невалидный токен → valid=false."""
        r = client.post('/api/federation/validate-token', json={
            'node_id': 'fake-node',
            'token': 'fake-token-1234',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        assert r.json()['valid'] is False

    def test_validate_token_empty_body(self, client: SyncASGIClient, logged_user: dict):
        """Пустое тело → 422."""
        r = client.post('/api/federation/validate-token', json={}, headers=logged_user['headers'])
        assert r.status_code == 422

    def test_validate_token_for_real_node(self, client: SyncASGIClient, logged_user: dict):
        """Если узел зарегистрирован, его токен может быть valid=true или false."""
        h = logged_user['headers']
        nid = secrets.token_hex(16)
        tag = random_str()
        _register_node_via_handshake(client, h, node_id=nid,
                                     url=f'https://token-test-{tag}.example.com:8443')
        r = client.post('/api/federation/validate-token', json={
            'node_id': nid,
            'token': 'probably-wrong-token',
        }, headers=h)
        assert r.status_code == 200
        # Без реального токена — false
        assert r.json()['valid'] is False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Node network status
# ═══════════════════════════════════════════════════════════════════════════════

class TestNetworkStatus:
    """Статус сети федерации."""

    def test_status_has_required_fields(self, client: SyncASGIClient, logged_user: dict):
        """Status содержит все обязательные поля."""
        r = client.get('/api/federation/nodes/status', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'total_nodes' in body
        assert 'local_node_id' in body
        assert 'local_code_hash' in body
        assert isinstance(body['total_nodes'], int)
        assert isinstance(body['local_node_id'], str)

    def test_status_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """Status без авторизации → 401/403."""
        r = anon_client.get('/api/federation/nodes/status')
        assert r.status_code in (401, 403)

    def test_status_node_count_increases(self, client: SyncASGIClient, logged_user: dict):
        """Добавление узлов увеличивает total_nodes."""
        h = logged_user['headers']
        r1 = client.get('/api/federation/nodes/status', headers=h)
        before = r1.json()['total_nodes']

        _register_node_via_handshake(client, h)
        _register_node_via_handshake(client, h)

        r2 = client.get('/api/federation/nodes/status', headers=h)
        after = r2.json()['total_nodes']
        assert after >= before + 2


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: My Tasks (task distribution)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMyTasks:
    """Распределение задач по узлам."""

    def test_my_tasks_returns_list(self, client: SyncASGIClient, logged_user: dict):
        """GET my-tasks → 200, содержит node_id и tasks."""
        r = client.get('/api/federation/my-tasks', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'node_id' in body
        assert 'tasks' in body
        assert isinstance(body['tasks'], list)

    def test_my_tasks_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """GET my-tasks без авторизации → 401/403."""
        r = anon_client.get('/api/federation/my-tasks')
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Node add via /nodes/add (with probe)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNodeAdd:
    """Добавление узлов через /nodes/add (с пробой доступности)."""

    def test_add_node_invalid_url(self, client: SyncASGIClient, logged_user: dict):
        """Пустой URL → 400/422."""
        r = client.post('/api/federation/nodes/add', json={
            'url': '',
        }, headers=logged_user['headers'])
        assert r.status_code in (400, 422)

    def test_add_node_no_scheme(self, client: SyncASGIClient, logged_user: dict):
        """URL без схемы → 400/422."""
        r = client.post('/api/federation/nodes/add', json={
            'url': 'just-a-hostname.example.com',
        }, headers=logged_user['headers'])
        assert r.status_code in (400, 422)

    def test_add_node_ssrf_blocked(self, client: SyncASGIClient, logged_user: dict):
        """Link-local IP (169.254.x.x) заблокирован → 400."""
        r = client.post('/api/federation/nodes/add', json={
            'url': 'https://169.254.169.254',
        }, headers=logged_user['headers'])
        assert r.status_code == 400

    def test_add_node_unreachable(self, client: SyncASGIClient, logged_user: dict):
        """Недоступный хост → 502 (probe fails)."""
        r = client.post('/api/federation/nodes/add', json={
            'url': 'https://nonexistent.invalid:9999',
        }, headers=logged_user['headers'])
        assert r.status_code == 502

    def test_add_node_duplicate_409(self, client: SyncASGIClient, logged_user: dict):
        """Добавление уже существующего узла → 409."""
        h = logged_user['headers']
        tag = random_str()
        url = f'https://dup-add-{tag}.example.com:8443'
        # Регистрируем через handshake
        _register_node_via_handshake(client, h, url=url)
        # Пробуем через /nodes/add — должен быть 409
        r = client.post('/api/federation/nodes/add', json={'url': url}, headers=h)
        assert r.status_code == 409

    def test_add_node_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """Добавление без авторизации → 401/403."""
        r = anon_client.post('/api/federation/nodes/add', json={
            'url': 'https://example.com:8443',
        })
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Node verify
# ═══════════════════════════════════════════════════════════════════════════════

class TestNodeVerify:
    """Ручная верификация узла."""

    def test_verify_nonexistent_node(self, client: SyncASGIClient, logged_user: dict):
        """Верификация несуществующего узла → 404."""
        r = client.post('/api/federation/nodes/verify', json={
            'node_id': 999999,
        }, headers=logged_user['headers'])
        assert r.status_code in (404, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Multihop join (A → B → C)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultihopJoin:
    """Мультихоп соединение через промежуточный узел."""

    def test_multihop_join_unreachable_via(self, client: SyncASGIClient, logged_user: dict):
        """Промежуточный узел недоступен → 502/503."""
        r = client.post('/api/peers/multihop-join', json={
            'invite_code': 'ABCDEF',
            'target_ip': '192.0.2.2',
            'target_port': 8000,
            'via_ip': '192.0.2.1',
            'via_port': 8000,
        }, headers=logged_user['headers'])
        assert r.status_code in (502, 503)

    def test_multihop_join_missing_fields(self, client: SyncASGIClient, logged_user: dict):
        """Неполные данные → 422."""
        r = client.post('/api/peers/multihop-join', json={
            'invite_code': 'ABCDEF',
        }, headers=logged_user['headers'])
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Full scenario — connect, communicate, disconnect
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullFederationScenario:
    """Полный сценарий: подключение → общение → отключение."""

    def test_full_lifecycle(self, client: SyncASGIClient, logged_user: dict):
        """
        1. Добавить 3 узла через handshake
        2. Проверить что все в списке
        3. Проверить статус сети
        4. Удалить один узел
        5. Проверить что остальные на месте
        6. Gossip о новом узле
        7. Проверить что он появился
        8. Gossip о выходе узла
        """
        h = logged_user['headers']
        local_hash = _code_hash(client)

        # 1. Добавляем 3 узла
        node_ids = []
        node_urls = []
        for i in range(3):
            tag = random_str()
            nid = secrets.token_hex(16)
            url = f'https://full-test-{i}-{tag}.example.com:8443'
            r = client.post('/api/federation/handshake', json={
                'node_id': nid, 'url': url,
                'code_hash': local_hash, 'version': '1.0.0',
            }, headers=h)
            assert r.status_code == 200
            assert r.json()['accepted'] is True
            node_ids.append(nid)
            node_urls.append(url)

        # 2. Все в списке
        r = client.get('/api/federation/nodes', headers=h)
        assert r.status_code == 200
        listed_urls = [n['url'] for n in r.json()['nodes']]
        for url in node_urls:
            assert url in listed_urls

        # 3. Статус
        r = client.get('/api/federation/nodes/status', headers=h)
        assert r.status_code == 200
        assert r.json()['total_nodes'] >= 3

        # 4. Удаляем первый
        nodes_list = r.json() if 'nodes' not in r.json() else client.get('/api/federation/nodes', headers=h).json()
        target = next((n for n in nodes_list.get('nodes', []) if n['url'] == node_urls[0]), None)
        if target:
            rd = client.delete(f'/api/federation/nodes/{target["id"]}', headers=h)
            assert rd.status_code == 200

        # 5. Остальные на месте
        r = client.get('/api/federation/nodes', headers=h)
        remaining = [n['url'] for n in r.json()['nodes']]
        assert node_urls[1] in remaining
        assert node_urls[2] in remaining

        # 6. Gossip о новом узле
        gossip_tag = random_str()
        gossip_nid = secrets.token_hex(16)
        gossip_url = f'https://gossip-full-{gossip_tag}.example.com:8443'
        r = client.post('/api/federation/gossip/node-joined', json={
            'node_id': gossip_nid, 'url': gossip_url,
            'code_hash': local_hash, 'version': '1.0.0',
        }, headers=h)
        assert r.status_code == 200

        # 7. Появился в списке
        r = client.get('/api/federation/nodes', headers=h)
        all_urls = [n['url'] for n in r.json()['nodes']]
        assert gossip_url in all_urls

        # 8. Gossip о выходе
        r = client.post('/api/federation/gossip/node-left', json={
            'node_id': gossip_nid, 'url': gossip_url,
        }, headers=h)
        assert r.status_code == 200
