"""
Middleware стек.

Порядок подключения (в main.py):
  1. SecurityHeadersMiddleware  — безопасные заголовки
  2. LoggingMiddleware          — логирование запросов
  3. CSRFMiddleware             — защита от CSRF
  4. TokenRefreshMiddleware     — автообновление JWT

WAF подключается отдельно как ASGI middleware.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import SessionLocal
from app.security.auth_jwt import verify_refresh_token, create_access_token

logger = logging.getLogger(__name__)
_IS_PROD = os.getenv("ENVIRONMENT", "development") == "production"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Устанавливает заголовки безопасности. CSP настроен для WebRTC и WebSocket."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            return response

        response.headers["X-Frame-Options"]              = "DENY"
        response.headers["X-Content-Type-Options"]       = "nosniff"
        response.headers["X-XSS-Protection"]             = "1; mode=block"
        response.headers["Referrer-Policy"]              = "strict-origin-when-cross-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Cross-Origin-Opener-Policy"]   = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        if _IS_PROD:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        else:
            response.headers["Strict-Transport-Security"] = "max-age=86400"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss: http: https:; "
            "media-src 'self' blob:; "
            "frame-src 'none'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        response.headers["Permissions-Policy"] = (
            "geolocation=(), payment=(), usb=(), "
            "microphone=(self), camera=(self)"
        )

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Логирует все HTTP запросы с временем обработки."""

    async def dispatch(self, request: Request, call_next):
        if (request.url.path.startswith("/static/")
                or request.headers.get("upgrade", "").lower() == "websocket"):
            return await call_next(request)

        start = time.perf_counter()
        ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Unhandled: {request.method} {request.url.path} — {e}", exc_info=True)
            return PlainTextResponse("Internal Server Error", status_code=500)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            f"{request.method:6s} {request.url.path:<40s} "
            f"{response.status_code} {elapsed:6.1f}ms  {ip}"
        )
        return response


class CSRFMiddleware(BaseHTTPMiddleware):

    _SAFE_METHODS  = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
    _SKIP_PATHS    = frozenset({
        "/api/files/upload-chunk/",
        "/api/files/upload-init",
        "/api/files/upload-complete/",
        "/health", "/favicon.ico", "/robots.txt",
        "/api/authentication/login", "/api/authentication/register",
        "/api/authentication/refresh",
        "/api/peers/receive",
        "/api/peers/status",
        "/api/peers/federated-join",
        "/api/federation/guest-login",
        "/api/docs",
    })
    _SKIP_PREFIXES = (
        "/static/", "/waf/", "/api/rooms/join/",
        "/api/files/upload-chunk/",
        "/api/files/upload-complete/",
        "/api/files/upload-cancel/",
        "/api/files/upload-status/",
        "/api/files/upload-init",
    )

    async def dispatch(self, request: Request, call_next):
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        path = request.url.path
        if path in self._SKIP_PATHS or any(path.startswith(p) for p in self._SKIP_PREFIXES):
            response = await call_next(request)
            self._set_csrf_cookie(response, request)
            return response

        csrf_cookie = request.cookies.get("csrf_token")
        if not csrf_cookie:
            csrf_cookie = secrets.token_urlsafe(32)

        request.state.csrf_token = csrf_cookie

        if request.method in self._SAFE_METHODS:
            response = await call_next(request)
            self._set_csrf_cookie(response, request, csrf_cookie)
            return response

        content_type = request.headers.get("content-type", "")
        submitted    = None

        try:
            if "application/json" in content_type:
                submitted = request.headers.get("x-csrf-token")
                if not submitted:
                    body_bytes = await request.body()
                    if body_bytes:
                        try:
                            body = json.loads(body_bytes.decode("utf-8", errors="ignore"))
                            submitted = body.get("csrf_token")
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    if not hasattr(request, "_body"):
                        request._body = body_bytes if body_bytes else b""

            elif "multipart/form-data" in content_type:
                submitted = request.headers.get("x-csrf-token")

            elif "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                for field_name in ("csrf_token", "_csrf", "csrf-token"):
                    if field_name in form:
                        submitted = form[field_name]
                        break
                if not submitted:
                    submitted = request.headers.get("x-csrf-token")
                request.state.form = form

            else:
                submitted = request.headers.get("x-csrf-token")

        except Exception as e:
            logger.error(f"CSRF read error: {e}", exc_info=True)
            return JSONResponse({"error": "Ошибка проверки CSRF"}, status_code=500)

        if not submitted:
            logger.warning(f"CSRF: нет токена для {request.method} {path}")
            return JSONResponse(
                {"error": "CSRF токен не предоставлен",
                 "hint": "Добавьте X-CSRF-Token заголовок или поле csrf_token"},
                status_code=403, headers={"X-CSRF-Required": "true"}
            )

        if not secrets.compare_digest(str(submitted), str(csrf_cookie)):
            logger.warning(f"CSRF: неверный токен для {path}")
            return JSONResponse(
                {"error": "Недействительный CSRF токен"},
                status_code=403, headers={"X-CSRF-Required": "true"}
            )

        response = await call_next(request)
        if response is None:
            return PlainTextResponse("Internal Server Error", status_code=500)
        self._set_csrf_cookie(response, request, csrf_cookie)
        return response

    @staticmethod
    def _set_csrf_cookie(response, request: Request, token: Optional[str] = None):
        if not request.cookies.get("csrf_token"):
            token = token or secrets.token_urlsafe(32)
            response.set_cookie(
                "csrf_token", token,
                httponly=False,
                secure=_IS_PROD,
                samesite="Lax",
                max_age=86400, path="/",
            )


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """Автоматически обновляет access_token если он отсутствует, но есть refresh_token."""

    _SKIP = frozenset({
        "/api/authentication/login", "/api/authentication/register",
        "/api/authentication/refresh",
        "/api/authentication/logout", "/health", "/favicon.ico",
    })

    async def dispatch(self, request: Request, call_next):
        if (request.url.path.startswith("/static/")
                or request.url.path in self._SKIP
                or request.headers.get("upgrade", "").lower() == "websocket"):
            return await call_next(request)

        if not request.cookies.get("access_token") and request.cookies.get("refresh_token"):
            try:
                db = SessionLocal()
                try:
                    raw = request.cookies["refresh_token"]
                    user = verify_refresh_token(raw, db)
                    new_token = create_access_token(user.id, user.phone, user.username)
                    response  = await call_next(request)
                    response.set_cookie(
                        "access_token", new_token,
                        httponly=True, secure=_IS_PROD,
                        samesite="Lax", max_age=3600, path="/",
                    )
                    return response
                finally:
                    db.close()
            except Exception as e:
                logger.debug(f"Token refresh failed: {e}")

        return await call_next(request)