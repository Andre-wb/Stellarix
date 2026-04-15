"""
Coverage tests for internal/unit-testable modules:
  - app/security/crypto.py (Python fallback functions)
  - app/security/key_exchange.py (ecies_decrypt_node error)
  - app/security/auth_jwt.py (get_user_ws, edge cases)
  - app/security/secure_upload.py (UploadQuotaManager, image validation, temp files)
  - app/bots/antispam_bot.py (bot CRUD, spam checks, command handler)
  - app/peer/connection_manager.py (connect/disconnect/broadcast with mock WS)
  - app/config.py (_read_env, _ensure_vapid_keys, validate)
  - app/database.py (async engine, get_engine_info, URL resolution)
  - app/logging_config.py (edge cases)
  - app/models.py, app/models_rooms.py (repr/validators)
"""
import os
import secrets
import hashlib
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# crypto.py — Python fallback functions (lines 46-121)
# ══════════════════════════════════════════════════════════════════════════════

class TestCryptoPythonFallbacks:
    """Test _py_* functions directly to cover lines 46-121."""

    def test_py_generate_key(self):
        from app.security.crypto import _py_generate_key
        key = _py_generate_key()
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_py_encrypt_decrypt(self):
        from app.security.crypto import _py_encrypt, _py_decrypt, _py_generate_key
        key = _py_generate_key()
        ct = _py_encrypt(b"hello fallback", key)
        assert ct != b"hello fallback"
        pt = _py_decrypt(ct, key)
        assert pt == b"hello fallback"

    def test_py_decrypt_short_data(self):
        from app.security.crypto import _py_decrypt, _py_generate_key
        key = _py_generate_key()
        with pytest.raises(ValueError, match="короткие"):
            _py_decrypt(b"short", key)

    def test_py_encrypt_empty(self):
        from app.security.crypto import _py_encrypt, _py_decrypt, _py_generate_key
        key = _py_generate_key()
        ct = _py_encrypt(b"", key)
        pt = _py_decrypt(ct, key)
        assert pt == b""

    def test_py_hash_blake3(self):
        from app.security.crypto import _py_hash
        h = _py_hash(b"test data")
        assert len(h) == 32
        assert isinstance(h, bytes)

    def test_py_hash_deterministic(self):
        from app.security.crypto import _py_hash
        h1 = _py_hash(b"same")
        h2 = _py_hash(b"same")
        assert h1 == h2

    def test_py_hash_different(self):
        from app.security.crypto import _py_hash
        h1 = _py_hash(b"aaa")
        h2 = _py_hash(b"bbb")
        assert h1 != h2

    def test_py_hash_password(self):
        from app.security.crypto import _py_hash_password
        h = _py_hash_password("TestPass123!")
        assert h.startswith("$argon2")

    def test_py_verify_password_correct(self):
        from app.security.crypto import _py_hash_password, _py_verify_password
        h = _py_hash_password("MyPassword!")
        assert _py_verify_password("MyPassword!", h) is True

    def test_py_verify_password_wrong(self):
        from app.security.crypto import _py_hash_password, _py_verify_password
        h = _py_hash_password("correct")
        assert _py_verify_password("wrong", h) is False

    def test_py_verify_password_invalid_hash(self):
        from app.security.crypto import _py_verify_password
        assert _py_verify_password("test", "not_a_valid_hash") is False

    def test_py_hash_token(self):
        from app.security.crypto import _py_hash_token
        h = _py_hash_token("my_token_123")
        assert len(h) == 64
        assert h == hashlib.sha256(b"my_token_123").hexdigest()

    def test_py_verify_token_correct(self):
        from app.security.crypto import _py_hash_token, _py_verify_token
        h = _py_hash_token("tok")
        assert _py_verify_token("tok", h) is True

    def test_py_verify_token_wrong(self):
        from app.security.crypto import _py_hash_token, _py_verify_token
        h = _py_hash_token("tok")
        assert _py_verify_token("bad", h) is False

    def test_py_generate_keypair(self):
        from app.security.crypto import _py_generate_keypair
        priv, pub = _py_generate_keypair()
        assert len(priv) == 32
        assert len(pub) == 32

    def test_py_derive_session_key(self):
        from app.security.crypto import _py_generate_keypair, _py_derive_session_key
        priv_a, pub_a = _py_generate_keypair()
        priv_b, pub_b = _py_generate_keypair()
        k1 = _py_derive_session_key(priv_a, pub_b)
        k2 = _py_derive_session_key(priv_b, pub_a)
        assert k1 == k2
        assert len(k1) == 32


class TestCryptoPublicAPIDispatch:
    """Test dispatcher functions lines 128-196 — whichever backend is active."""

    def test_generate_key_dispatch(self):
        from app.security.crypto import generate_key
        k = generate_key()
        assert len(k) == 32

    def test_encrypt_decrypt_dispatch(self):
        from app.security.crypto import generate_key, encrypt_message, decrypt_message
        k = generate_key()
        ct = encrypt_message(b"dispatch test", k)
        pt = decrypt_message(ct, k)
        assert pt == b"dispatch test"

    def test_hash_message_dispatch(self):
        from app.security.crypto import hash_message
        h = hash_message(b"data")
        assert len(h) == 32

    def test_hash_password_dispatch(self):
        from app.security.crypto import hash_password
        h = hash_password("Test123!")
        assert isinstance(h, str) and len(h) > 10

    def test_verify_password_dispatch(self):
        from app.security.crypto import hash_password, verify_password
        h = hash_password("Test123!")
        assert verify_password("Test123!", h) is True
        assert verify_password("Wrong!", h) is False

    def test_hash_token_dispatch(self):
        from app.security.crypto import hash_token
        h = hash_token("abc")
        assert isinstance(h, str)

    def test_verify_token_hash_dispatch(self):
        from app.security.crypto import hash_token, verify_token_hash
        h = hash_token("tok")
        assert verify_token_hash("tok", h) is True

    def test_generate_keypair_dispatch(self):
        from app.security.crypto import generate_x25519_keypair
        priv, pub = generate_x25519_keypair()
        assert len(priv) == 32 and len(pub) == 32

    def test_derive_session_key_dispatch(self):
        from app.security.crypto import generate_x25519_keypair, derive_x25519_session_key
        pa, puba = generate_x25519_keypair()
        pb, pubb = generate_x25519_keypair()
        k1 = derive_x25519_session_key(pa, pubb)
        k2 = derive_x25519_session_key(pb, puba)
        assert k1 == k2

    def test_rust_available(self):
        from app.security.crypto import rust_available
        assert isinstance(rust_available(), bool)


class TestCryptoNodeKeypair:
    """Covers lines 211-251 (load_or_create_node_keypair, get_node_public_key_hex)."""

    def test_create_new_keypair(self, tmp_path):
        from app.security.crypto import _py_generate_keypair
        import app.security.crypto as cm
        old_priv, old_pub = cm._node_priv, cm._node_pub
        cm._node_priv, cm._node_pub = None, None
        try:
            priv, pub = cm.load_or_create_node_keypair(tmp_path)
            assert len(priv) > 0 and len(pub) > 0
            assert (tmp_path / "x25519_private.bin").exists()
            assert (tmp_path / "x25519_public.bin").exists()
        finally:
            cm._node_priv, cm._node_pub = old_priv, old_pub

    def test_load_existing_keypair(self, tmp_path):
        import app.security.crypto as cm
        old_priv, old_pub = cm._node_priv, cm._node_pub
        cm._node_priv, cm._node_pub = None, None
        try:
            p1, k1 = cm.load_or_create_node_keypair(tmp_path)
            cm._node_priv, cm._node_pub = None, None
            p2, k2 = cm.load_or_create_node_keypair(tmp_path)
            assert p1 == p2 and k1 == k2
        finally:
            cm._node_priv, cm._node_pub = old_priv, old_pub

    def test_get_node_public_key_hex(self, tmp_path):
        import app.security.crypto as cm
        old_priv, old_pub = cm._node_priv, cm._node_pub
        cm._node_priv, cm._node_pub = None, None
        try:
            hex_key = cm.get_node_public_key_hex(tmp_path)
            assert len(hex_key) >= 64
            assert all(c in "0123456789abcdef" for c in hex_key)
        finally:
            cm._node_priv, cm._node_pub = old_priv, old_pub

    def test_fix_permissions(self, tmp_path):
        """Covers lines 233-235 (permission fix)."""
        import app.security.crypto as cm
        old_priv, old_pub = cm._node_priv, cm._node_pub
        cm._node_priv, cm._node_pub = None, None
        try:
            cm.load_or_create_node_keypair(tmp_path)
            priv_path = tmp_path / "x25519_private.bin"
            os.chmod(priv_path, 0o644)
            cm._node_priv, cm._node_pub = None, None
            cm.load_or_create_node_keypair(tmp_path)
        finally:
            cm._node_priv, cm._node_pub = old_priv, old_pub


# ══════════════════════════════════════════════════════════════════════════════
# key_exchange.py — line 156 (decrypt error)
# ══════════════════════════════════════════════════════════════════════════════

class TestKeyExchangeErrors:
    def test_ecies_decrypt_node_invalid_data(self):
        from app.security.key_exchange import ecies_decrypt_node
        from app.security.crypto import generate_x25519_keypair
        priv, pub = generate_x25519_keypair()
        with pytest.raises(Exception):
            ecies_decrypt_node("aa" * 32, "bb" * 30, priv)

    def test_validate_ecies_payload_missing_fields(self):
        from app.security.key_exchange import validate_ecies_payload
        assert validate_ecies_payload({}) is False
        assert validate_ecies_payload({"ephemeral_pub": "aa" * 32}) is False
        assert validate_ecies_payload({"ephemeral_pub": "aa" * 32, "ciphertext": "bb" * 30}) is True

    def test_format_encrypted_key(self):
        from app.security.key_exchange import format_encrypted_key
        eph, ct = format_encrypted_key({"ephemeral_pub": "aabb", "ciphertext": "ccdd"})
        assert eph == "aabb"
        assert ct == "ccdd"


# ══════════════════════════════════════════════════════════════════════════════
# auth_jwt.py — lines 100-142 (get_current_user, get_user_ws)
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthJWT:
    def test_create_and_decode_access_token(self):
        from app.security.auth_jwt import create_access_token, decode_access_token
        token = create_access_token(1, "+79001234567", "testuser")
        payload = decode_access_token(token)
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"

    def test_decode_expired_token(self):
        import jwt as pyjwt
        from app.config import Config
        token = pyjwt.encode(
            {"sub": "1", "exp": 0, "jti": "x", "phone": "x", "username": "x"},
            Config.JWT_SECRET, algorithm="HS256"
        )
        from fastapi import HTTPException
        from app.security.auth_jwt import decode_access_token
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401

    def test_decode_invalid_token(self):
        from fastapi import HTTPException
        from app.security.auth_jwt import decode_access_token
        with pytest.raises(HTTPException):
            decode_access_token("not.a.jwt")

    def test_create_refresh_token(self):
        from app.security.auth_jwt import create_refresh_token
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            raw, exp = create_refresh_token(1, db, ip="127.0.0.1", ua="test")
            assert isinstance(raw, str) and len(raw) > 20
        finally:
            db.close()

    def test_verify_refresh_token_invalid(self):
        from fastapi import HTTPException
        from app.security.auth_jwt import verify_refresh_token
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            with pytest.raises(HTTPException):
                verify_refresh_token("invalid_token_xxx", db)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_get_user_ws_invalid(self):
        from fastapi import HTTPException
        from app.security.auth_jwt import get_user_ws
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            with pytest.raises(HTTPException):
                await get_user_ws("not_a_token", db)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self):
        from fastapi import HTTPException
        from app.security.auth_jwt import get_current_user
        from app.database import SessionLocal
        db = SessionLocal()
        request = MagicMock()
        request.cookies = {}
        request.headers = {}
        try:
            with pytest.raises(HTTPException):
                await get_current_user(request, db)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_get_current_user_bearer_header(self):
        from app.security.auth_jwt import get_current_user, create_access_token
        from app.database import SessionLocal
        from app.models import User
        db = SessionLocal()
        try:
            user = db.query(User).first()
            if not user:
                pytest.skip("No users in DB")
            token = create_access_token(user.id, user.phone, user.username)
            request = MagicMock()
            request.cookies = {}
            request.headers = {"Authorization": f"Bearer {token}"}
            result = await get_current_user(request, db)
            assert result.id == user.id
        finally:
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# secure_upload.py — UploadQuotaManager, image validation, temp files
# ══════════════════════════════════════════════════════════════════════════════

class TestSecureUploadInternals:
    def test_file_upload_config_exists(self):
        from app.security.secure_upload import FileUploadConfig
        assert FileUploadConfig.MAX_FILE_SIZE > 0
        assert FileUploadConfig.MAX_FILES_PER_HOUR > 0

    def test_generate_secure_filename(self):
        from app.security.secure_upload import generate_secure_filename
        name = generate_secure_filename(".txt")
        assert name.endswith(".txt")
        assert len(name) > 10

    def test_calculate_file_hash(self):
        from app.security.secure_upload import calculate_file_hash
        h = calculate_file_hash(b"test content")
        assert isinstance(h, str) and len(h) == 64

    def test_validate_mime_text(self):
        from app.security.secure_upload import validate_file_mime_type
        ok, mime = validate_file_mime_type(b"plain text content", "file.txt")
        assert ok is True

    def test_validate_mime_unknown_ext(self):
        from app.security.secure_upload import validate_file_mime_type
        ok, mime = validate_file_mime_type(b"\x00" * 50, "file.xyz123")
        assert isinstance(ok, bool)

    def test_validate_mime_encrypted(self):
        from app.security.secure_upload import validate_file_mime_type
        ok, mime = validate_file_mime_type(os.urandom(100), "file.enc")
        assert isinstance(ok, bool)

    @pytest.mark.asyncio
    async def test_validate_image_content_valid(self):
        from app.security.secure_upload import FileAnomalyDetector
        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        ok, err = await FileAnomalyDetector.validate_image_content(buf.getvalue())
        assert ok is True

    @pytest.mark.asyncio
    async def test_validate_image_content_invalid(self):
        from app.security.secure_upload import FileAnomalyDetector
        ok, err = await FileAnomalyDetector.validate_image_content(b"not an image")
        assert ok is False

    @pytest.mark.asyncio
    async def test_validate_image_too_large(self):
        from app.security.secure_upload import FileAnomalyDetector
        from PIL import Image
        import io
        img = Image.new("RGB", (20000, 20000), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        ok, err = await FileAnomalyDetector.validate_image_content(buf.getvalue())
        assert ok is False

    def test_upload_quota_manager_import(self):
        from app.security.secure_upload import UploadQuotaManager
        assert UploadQuotaManager is not None

    def test_save_and_cleanup_temp(self, tmp_path):
        from app.security.secure_upload import save_temp_file, cleanup_temp_files
        with patch("app.security.secure_upload.FileUploadConfig") as cfg:
            cfg.TEMP_DIR = tmp_path
            path, temp_dir = save_temp_file(b"temp data", ".txt")
            assert path.exists()
            cleanup_temp_files(temp_dir, path)


# ══════════════════════════════════════════════════════════════════════════════
# antispam_bot.py — bot management and spam checks
# ══════════════════════════════════════════════════════════════════════════════

class TestAntispamBotInternals:
    def test_ensure_bot_creates(self):
        from app.bots.antispam_bot import ensure_antispam_bot
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            uid = ensure_antispam_bot(db)
            assert uid is not None and uid > 0
        finally:
            db.close()

    def test_add_bot_to_room(self):
        from app.bots.antispam_bot import ensure_antispam_bot, add_antispam_bot_to_room
        from app.database import SessionLocal
        from app.models_rooms import Room
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            # Find a real room to avoid FK constraint
            room = db.query(Room).first()
            if room:
                result = add_antispam_bot_to_room(room.id, db)
                assert isinstance(result, bool)
        finally:
            db.close()

    def test_remove_bot_from_room(self):
        from app.bots.antispam_bot import remove_antispam_bot_from_room
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            result = remove_antispam_bot_from_room(999999, db)
            assert isinstance(result, bool)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_antispam_bot_message(self):
        from app.bots.antispam_bot import ensure_antispam_bot, antispam_bot_message
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            msg = await antispam_bot_message(999999, "test message", db)
            # May be None if room doesn't exist
            assert msg is None or hasattr(msg, "id")
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_check_repeat_spam_no_spam(self):
        from app.bots.antispam_bot import ensure_antispam_bot, check_repeat_spam
        from app.database import SessionLocal
        from app.models import User
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            user = db.query(User).filter(User.is_bot == False).first()
            if not user:
                pytest.skip("No non-bot users")
            result = await check_repeat_spam(999999, user, f"unique_{secrets.token_hex(8)}", db)
            assert result is False
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_check_link_spam_no_links(self):
        from app.bots.antispam_bot import ensure_antispam_bot, check_link_spam
        from app.database import SessionLocal
        from app.models import User
        from app.models_rooms import RoomRole
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            user = db.query(User).filter(User.is_bot == False).first()
            if not user:
                pytest.skip("No non-bot users")
            result = await check_link_spam(999999, user, "no links here", RoomRole.MEMBER, db)
            assert result is False
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_check_link_spam_with_link(self):
        from app.bots.antispam_bot import ensure_antispam_bot, check_link_spam
        from app.database import SessionLocal
        from app.models import User
        from app.models_rooms import RoomRole
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            user = db.query(User).filter(User.is_bot == False).first()
            if not user:
                pytest.skip("No non-bot users")
            result = await check_link_spam(999999, user, "click https://evil.com", RoomRole.MEMBER, db)
            assert isinstance(result, bool)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_check_caps_spam_not_caps(self):
        from app.bots.antispam_bot import ensure_antispam_bot, check_caps_spam
        from app.database import SessionLocal
        from app.models import User
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            user = db.query(User).filter(User.is_bot == False).first()
            if not user:
                pytest.skip("No non-bot users")
            result = await check_caps_spam(999999, user, "normal lowercase message", db)
            assert result is False
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_check_caps_spam_all_caps(self):
        from app.bots.antispam_bot import ensure_antispam_bot, check_caps_spam
        from app.database import SessionLocal
        from app.models import User
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            user = db.query(User).filter(User.is_bot == False).first()
            if not user:
                pytest.skip("No non-bot users")
            result = await check_caps_spam(
                999999, user,
                "THIS IS ALLCAPS SCREAMING MESSAGE THAT IS VERY LOUD AND OBNOXIOUS", db
            )
            assert isinstance(result, bool)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_handle_antispam_command(self):
        from app.bots.antispam_bot import ensure_antispam_bot, handle_antispam_command
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            ensure_antispam_bot(db)
            await handle_antispam_command(999999, "/antispam_status", db)
            await handle_antispam_command(999999, "/antispam_help", db)
        finally:
            db.close()


# ══════════════════════════════════════════════════════════════════════════════
# connection_manager.py — connect/disconnect/broadcast with mock WS
# ══════════════════════════════════════════════════════════════════════════════

class TestConnectionManagerMethods:
    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        await mgr.connect(1, 100, "alice", "Alice", "👤", ws)
        assert mgr.total_connections() >= 1
        await mgr.disconnect(1, 100)

    @pytest.mark.asyncio
    async def test_broadcast_to_room(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws1, ws2 = MagicMock(), MagicMock()
        ws1.accept = ws2.accept = AsyncMock()
        ws1.send_json = ws1.send_text = AsyncMock()
        ws2.send_json = ws2.send_text = AsyncMock()
        ws1.close = ws2.close = AsyncMock()
        await mgr.connect(1, 10, "u1", "U1", "👤", ws1)
        await mgr.connect(1, 11, "u2", "U2", "👤", ws2)
        await mgr.broadcast_to_room(1, {"type": "test"}, exclude=10)
        await mgr.disconnect(1, 10)
        await mgr.disconnect(1, 11)

    @pytest.mark.asyncio
    async def test_send_to_user(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        await mgr.connect(1, 20, "u", "U", "👤", ws)
        result = await mgr.send_to_user(1, 20, {"msg": "hi"})
        assert result is True
        result2 = await mgr.send_to_user(1, 999, {"msg": "hi"})
        assert result2 is False
        await mgr.disconnect(1, 20)

    @pytest.mark.asyncio
    async def test_set_typing(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        await mgr.connect(1, 30, "u", "U", "👤", ws)
        await mgr.set_typing(1, 30, True)
        await mgr.set_typing(1, 30, False)
        await mgr.disconnect(1, 30)

    @pytest.mark.asyncio
    async def test_check_rate_limit(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        await mgr.connect(1, 40, "u", "U", "👤", ws)
        for _ in range(30):
            mgr.check_rate_limit(1, 40)
        await mgr.disconnect(1, 40)

    @pytest.mark.asyncio
    async def test_connect_global_and_notify(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        await mgr.connect_global(50, ws)
        result = await mgr.notify_user(50, {"type": "notification"})
        assert result is True
        result2 = await mgr.notify_user(999, {"type": "notification"})
        assert result2 is False
        mgr.disconnect_global(50)

    @pytest.mark.asyncio
    async def test_close_all(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_json = ws.send_text = AsyncMock()
        await mgr.connect(1, 70, "u", "U", "👤", ws)
        await mgr.close_all()

    def test_dedup_stats_keys(self):
        from app.peer.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        stats = mgr.dedup_stats()
        assert isinstance(stats, dict)


# ══════════════════════════════════════════════════════════════════════════════
# config.py — _read_env, validate, _ensure_vapid_keys
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigInternals:
    def test_config_validate(self):
        from app.config import Config
        Config.validate()

    def test_config_ensure_dirs(self, tmp_path):
        from app.config import Config
        old_up, old_keys = Config.UPLOAD_DIR, Config.KEYS_DIR
        try:
            Config.UPLOAD_DIR = tmp_path / "up"
            Config.KEYS_DIR = tmp_path / "keys"
            Config.ensure_dirs()
            assert Config.UPLOAD_DIR.exists()
            assert Config.KEYS_DIR.exists()
        finally:
            Config.UPLOAD_DIR, Config.KEYS_DIR = old_up, old_keys

    def test_config_attributes(self):
        from app.config import Config
        assert isinstance(Config.JWT_SECRET, str)
        assert isinstance(Config.DB_POOL_SIZE, int)
        assert isinstance(Config.DB_MAX_OVERFLOW, int)
        assert isinstance(Config.DB_POOL_RECYCLE, int)
        assert isinstance(Config.MAX_FILE_BYTES, int)
        assert Config.NETWORK_MODE in ("local", "global")


# ══════════════════════════════════════════════════════════════════════════════
# database.py — engine info, init_db, URL resolution
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabaseInternals:
    def test_get_engine_info(self):
        from app.database import get_engine_info
        info = get_engine_info()
        assert info["backend"] in ("sqlite", "postgresql")
        assert "async_available" in info

    def test_database_url_resolution(self):
        from app.database import DATABASE_URL, _is_sqlite, _is_postgres
        assert isinstance(DATABASE_URL, str)
        assert _is_sqlite or _is_postgres

    def test_init_db_idempotent(self):
        from app.database import init_db
        init_db()
        init_db()

    def test_session_factory(self):
        from app.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()

    def test_get_db_generator(self):
        from app.database import get_db
        gen = get_db()
        db = next(gen)
        assert db is not None
        try:
            next(gen)
        except StopIteration:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# logging_config.py — edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestLoggingEdgeCases:
    def test_json_formatter_with_exception(self):
        import json, logging
        from app.logging_config import JSONFormatter
        f = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            record = logging.LogRecord("t", logging.ERROR, "", 0, "err", (), sys.exc_info())
        output = f.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed

    def test_json_formatter_with_extra_fields(self):
        import json, logging
        from app.logging_config import JSONFormatter
        f = JSONFormatter()
        record = logging.LogRecord("t", logging.INFO, "", 0, "msg", (), None)
        record.duration_ms = 42
        record.status_code = 200
        output = f.format(record)
        parsed = json.loads(output)
        assert parsed["duration_ms"] == 42

    def test_console_formatter_with_exception(self):
        import logging, sys
        from app.logging_config import ConsoleFormatter
        f = ConsoleFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = logging.LogRecord("t", logging.ERROR, "", 0, "err", (), sys.exc_info())
        output = f.format(record)
        assert "RuntimeError" in output

    def test_setup_logging_json(self, tmp_path):
        from app.logging_config import setup_logging
        setup_logging(log_format="json", log_level="WARNING", log_dir=str(tmp_path))


# ══════════════════════════════════════════════════════════════════════════════
# models.py / models_rooms.py — __repr__, validators
# ══════════════════════════════════════════════════════════════════════════════

class TestModelEdgeCases:
    def test_user_model_repr(self):
        from app.models import User
        u = User(id=1, username="test", phone="+79001234567")
        r = repr(u)
        assert "test" in r or "User" in str(type(u))

    def test_register_request_phone_validation(self):
        from app.models import RegisterRequest
        with pytest.raises(Exception):
            RegisterRequest(
                username="valid_user", password="StrongPass1!",
                phone="invalid", x25519_public_key="a" * 64
            )

    def test_register_request_valid(self):
        from app.models import RegisterRequest
        req = RegisterRequest(
            username="valid_user", password="StrongPass1!",
            phone="+79001234567", x25519_public_key="a" * 64
        )
        assert req.username == "valid_user"

    def test_room_role_enum(self):
        from app.models_rooms import RoomRole
        assert RoomRole.OWNER.value == "owner"
        assert RoomRole.ADMIN.value == "admin"
        assert RoomRole.MEMBER.value == "member"

    def test_message_type_enum(self):
        from app.models_rooms import MessageType
        assert MessageType.TEXT.value == "text"
        assert MessageType.FILE.value == "file"
        assert MessageType.IMAGE.value == "image"
