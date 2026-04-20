"""Passkey / WebAuthn — регистрация и аутентификация через биометрию / ключ."""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
import time

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security.auth_jwt import get_current_user

from app.security.ip_privacy import raw_ip_for_ratelimit

from app.authentication._helpers import (
    _AUTH_RATE_LOGIN, _check_auth_rate, _set_auth_cookies, router,
)

logger = logging.getLogger(__name__)

# ── Storage ───────────────────────────────────────────────────────────────

_passkey_challenges: dict[str, tuple[bytes, float, int]] = {}
_passkey_lock = threading.Lock()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _get_rp_id(request: Request) -> str:
    host = request.headers.get("host", "localhost")
    return host.split(":")[0]


def _get_origin(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost:8000")
    return f"{scheme}://{host}"


# ── Registration ──────────────────────────────────────────────────────────

@router.post("/passkey/register-options")
async def passkey_register_options(
    request: Request,
    u: User = Depends(get_current_user),
):
    """Шаг 1: PublicKeyCredentialCreationOptions для navigator.credentials.create()."""
    ip = raw_ip_for_ratelimit(request)
    if not _check_auth_rate(ip, _AUTH_RATE_LOGIN):
        raise HTTPException(429, "Too many attempts")

    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    rp_id = _get_rp_id(request)

    # Hardware-key enforcement: when REQUIRE_HARDWARE_KEY=true, we force
    # cross-platform authenticators (YubiKey, SoloKey, etc.) and REQUIRE
    # user verification — platform biometrics alone aren't enough.
    require_hw = os.getenv("REQUIRE_HARDWARE_KEY", "").lower() in ("1", "true", "yes")
    selection = (
        AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        if require_hw
        else AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
    )

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Vortex",
        user_id=str(u.id).encode(),
        user_name=u.username,
        user_display_name=u.display_name or u.username,
        authenticator_selection=selection,
    )

    session_id = secrets.token_hex(16)
    with _passkey_lock:
        _passkey_challenges[session_id] = (options.challenge, time.monotonic() + 300, u.id)

    return {
        "session_id": session_id,
        "options": json.loads(options_to_json(options)),
    }


class PasskeyRegisterVerify(BaseModel):
    session_id: str
    credential: dict


@router.post("/passkey/register-verify")
async def passkey_register_verify(
    body: PasskeyRegisterVerify,
    request: Request,
    u: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Шаг 2: Верифицируем attestation и сохраняем credential."""
    from webauthn import verify_registration_response
    from webauthn.helpers.structs import RegistrationCredential

    with _passkey_lock:
        ch_data = _passkey_challenges.pop(body.session_id, None)
    if not ch_data or time.monotonic() > ch_data[1]:
        raise HTTPException(401, "Session expired")
    if ch_data[2] != u.id:
        raise HTTPException(403, "Verification error")

    challenge = ch_data[0]
    rp_id = _get_rp_id(request)
    origin = _get_origin(request)

    try:
        credential = RegistrationCredential.parse_raw(json.dumps(body.credential))
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except Exception as e:
        logger.warning(f"Passkey register verify failed for user={u.id}: {e}")
        raise HTTPException(400, f"Verification error: {e}")

    u.passkey_credential_id = _b64url_encode(verification.credential_id)
    u.passkey_public_key = _b64url_encode(verification.credential_public_key)
    u.passkey_sign_count = verification.sign_count
    db.commit()

    logger.info(f"Passkey registered for user={u.username} (id={u.id})")
    return {"ok": True, "credential_id": u.passkey_credential_id}


# ── Login ─────────────────────────────────────────────────────────────────

@router.post("/passkey/login-options")
async def passkey_login_options(request: Request):
    """Шаг 1 входа: PublicKeyCredentialRequestOptions."""
    ip = raw_ip_for_ratelimit(request)
    if not _check_auth_rate(ip, _AUTH_RATE_LOGIN):
        raise HTTPException(429, "Too many attempts")

    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    rp_id = _get_rp_id(request)

    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    session_id = secrets.token_hex(16)
    with _passkey_lock:
        _passkey_challenges[session_id] = (options.challenge, time.monotonic() + 300, 0)

    return {
        "session_id": session_id,
        "options": json.loads(options_to_json(options)),
    }


class PasskeyLoginVerify(BaseModel):
    session_id: str
    credential: dict


@router.post("/passkey/login-verify")
async def passkey_login_verify(
    body: PasskeyLoginVerify,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Шаг 2 входа: Верифицируем assertion и выдаём JWT cookies."""
    from webauthn import verify_authentication_response
    from webauthn.helpers.structs import AuthenticationCredential

    ip = raw_ip_for_ratelimit(request)
    if not _check_auth_rate(ip, _AUTH_RATE_LOGIN):
        raise HTTPException(429, "Too many attempts")

    with _passkey_lock:
        ch_data = _passkey_challenges.pop(body.session_id, None)
    if not ch_data or time.monotonic() > ch_data[1]:
        raise HTTPException(401, "Session expired")

    challenge = ch_data[0]
    rp_id = _get_rp_id(request)
    origin = _get_origin(request)

    try:
        credential = AuthenticationCredential.parse_raw(json.dumps(body.credential))
    except Exception as e:
        raise HTTPException(400, f"Invalid credential: {e}")

    cred_id_b64 = _b64url_encode(credential.raw_id)
    user = db.query(User).filter(
        User.passkey_credential_id == cred_id_b64,
        User.is_active == True,
    ).first()
    if not user:
        raise HTTPException(401, "Verification error")

    try:
        stored_public_key = _b64url_decode(user.passkey_public_key)
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=stored_public_key,
            credential_current_sign_count=user.passkey_sign_count or 0,
        )
    except Exception as e:
        logger.warning(f"Passkey login verify failed for cred={cred_id_b64}: {e}")
        raise HTTPException(401, f"Verification error: {e}")

    user.passkey_sign_count = verification.new_sign_count
    db.commit()
    logger.info(f"Passkey login: user={user.username} (id={user.id})")

    data = {
        "ok": True,
        "user_id": user.id,
        "username": user.username,
        "phone": user.phone,
        "display_name": user.display_name or user.username,
        "avatar_emoji": user.avatar_emoji,
        "avatar_url": user.avatar_url,
        "email": user.email,
        "x25519_public_key": user.x25519_public_key,
    }
    resp = JSONResponse(content=data)
    _set_auth_cookies(resp, user, db, request)
    return resp
