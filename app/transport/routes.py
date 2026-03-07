"""
app/transport/routes.py — REST API для управления транспортами.

Endpoints:
  GET  /api/transport/status          — статус всех транспортов
  POST /api/transport/signal          — принять ICE кандидаты (signaling для hole punch)
  POST /api/transport/punch/{peer_ip} — инициировать NAT hole punch к пиру
  GET  /api/transport/ble/peers       — список BLE пиров
  GET  /api/transport/wifi-direct/peers — список Wi-Fi Direct пиров
  POST /api/transport/wifi-direct/connect — подключиться к P2P пиру
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.models import User
from app.security.auth_jwt import get_current_user
from app.transport.transport_manager import transport_manager
from app.transport.nat_traversal import signaling, hole_puncher, StunClient
from app.transport.ble_transport import ble_manager
from app.transport.wifi_direct import wifi_direct_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/transport", tags=["transport"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic схемы
# ─────────────────────────────────────────────────────────────────────────────

class SignalRequest(BaseModel):
    """Входящие ICE кандидаты от пира (для NAT hole punch signaling)."""
    session_id: str
    role:       str        # "initiator" | "responder"
    candidates: list[dict]


class HolePunchRequest(BaseModel):
    peer_ip:   str
    peer_port: int = 8000


class WifiDirectConnectRequest(BaseModel):
    peer_mac: str
    method:   str = "pbc"   # "pbc" | "pin"
    pin:      Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status")
async def transport_status(u: User = Depends(get_current_user)):
    """
    Возвращает полный статус всех транспортных подсистем:
      - NAT: внешний IP (STUN), активные hole punch сессии
      - BLE: доступность, список пиров, RSSI
      - Wi-Fi Direct: доступность, интерфейс, пиры
    """
    return transport_manager.full_status()


@router.get("/status/public")
async def transport_status_public():
    """
    Публичный статус без аутентификации.
    Используется другими узлами для проверки доступных транспортов.
    """
    status = transport_manager.full_status()
    return {
        "external_ip":   status.get("external_ip"),
        "external_port": status.get("external_port"),
        "ble_available": status.get("ble", {}).get("available", False),
        "wifi_direct_available": status.get("wifi_direct", {}).get("available", False),
    }


@router.post("/signal")
async def receive_signal(body: SignalRequest):
    """
    Принимает ICE кандидаты от другого узла.

    Этот endpoint вызывается в процессе NAT hole punching:
      Node A собирает кандидатов → POST /api/transport/signal на Node B
      Node B собирает кандидатов → POST /api/transport/signal на Node A
      Оба запускают punch() одновременно
    """
    transport_manager.accept_signal(
        session_id = body.session_id,
        role       = body.role,
        candidates = body.candidates,
    )
    return {"ok": True, "session_id": body.session_id}


@router.post("/punch")
async def initiate_hole_punch(
        body: HolePunchRequest,
        background_tasks: BackgroundTasks,
        u: User = Depends(get_current_user),
):
    """
    Инициирует NAT hole punch к указанному пиру.

    Процесс занимает несколько секунд, поэтому статус можно проверить
    через GET /api/transport/status после завершения.
    """
    background_tasks.add_task(
        transport_manager.initiate_hole_punch,
        peer_ip   = body.peer_ip,
        peer_port = body.peer_port,
    )
    return {
        "ok":      True,
        "message": f"Hole punch к {body.peer_ip}:{body.peer_port} запущен",
    }


@router.post("/punch/sync")
async def initiate_hole_punch_sync(
        body: HolePunchRequest,
        u: User = Depends(get_current_user),
):
    """
    Синхронный hole punch — ждёт результата (до 15 секунд).
    Удобно для UI: можно показать сразу успех/неудачу.
    """
    success = await transport_manager.initiate_hole_punch(
        peer_ip   = body.peer_ip,
        peer_port = body.peer_port,
    )
    return {
        "success":   success,
        "peer_ip":   body.peer_ip,
        "transport": "udp_hole_punch" if success else "relay_fallback",
    }


# ─────────────────────────────────────────────────────────────────────────────
# BLE Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ble/peers")
async def ble_peers(u: User = Depends(get_current_user)):
    """Список BLE пиров с уровнем сигнала (RSSI)."""
    peers = ble_manager.get_peers()
    return {
        "available": ble_manager.available,
        "count":     len(peers),
        "peers":     [p.to_dict() for p in peers],
    }


@router.post("/ble/scan")
async def ble_scan_now(u: User = Depends(get_current_user)):
    """Принудительный немедленный BLE-скан."""
    if not ble_manager.available:
        raise HTTPException(503, "BLE недоступен на этом устройстве")
    # Запускаем внеплановый скан
    await ble_manager._do_scan()
    return {"ok": True, "peers": len(ble_manager.get_peers())}


@router.post("/ble/send/{peer_address}")
async def ble_send_message(
        peer_address: str,
        payload: dict,
        u: User = Depends(get_current_user),
):
    """Отправить сообщение конкретному BLE пиру (MAC адрес)."""
    if not ble_manager.available:
        raise HTTPException(503, "BLE недоступен")

    ok = await ble_manager.send_message(peer_address, payload)
    if not ok:
        raise HTTPException(502, f"Не удалось отправить через BLE к {peer_address}")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Wi-Fi Direct Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/wifi-direct/peers")
async def wifi_direct_peers(u: User = Depends(get_current_user)):
    """Список обнаруженных Wi-Fi Direct пиров."""
    return wifi_direct_manager.status()


@router.post("/wifi-direct/connect")
async def wifi_direct_connect(
        body: WifiDirectConnectRequest,
        u: User = Depends(get_current_user),
):
    """
    Подключиться к Wi-Fi Direct пиру.

    PBC (Push Button): обе стороны должны инициировать подключение одновременно.
    PIN: передать PIN код пира.
    """
    if not wifi_direct_manager.available:
        raise HTTPException(503, "Wi-Fi Direct недоступен на этом устройстве")

    if body.method == "pin" and body.pin:
        # Linux PIN connect
        wpa = wifi_direct_manager._wpa
        if wpa:
            ok = await wpa.p2p_connect_pin(body.peer_mac, body.pin)
            return {"ok": ok, "method": "pin"}
    else:
        # PBC connect
        ip = await wifi_direct_manager.connect_pbc(body.peer_mac)
        if ip:
            return {"ok": True, "method": "pbc", "peer_ip": ip}
        raise HTTPException(502, f"P2P PBC connect к {body.peer_mac} не удался")

    return {"ok": False}


@router.post("/wifi-direct/create-group")
async def wifi_direct_create_group(u: User = Depends(get_current_user)):
    """
    Создать Wi-Fi Direct группу (этот узел становится Group Owner).
    Другие устройства могут подключаться без точки доступа.
    """
    if not wifi_direct_manager.available or not wifi_direct_manager._wpa:
        raise HTTPException(503, "Wi-Fi Direct недоступен")

    iface = await wifi_direct_manager._wpa.p2p_group_add()
    if not iface:
        raise HTTPException(502, "Не удалось создать P2P группу")

    ip = await wifi_direct_manager._wpa.get_p2p_ip(iface)
    return {
        "ok":        True,
        "interface": iface,
        "ip":        ip,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STUN / NAT Info
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/nat/info")
async def nat_info(u: User = Depends(get_current_user)):
    """Информация о NAT: внешний IP, порт, активные hole punch сессии."""
    # Свежий STUN запрос
    external = await StunClient.discover_external()

    return {
        "external_ip":       external[0] if external else transport_manager._external_ip,
        "external_port":     external[1] if external else transport_manager._external_port,
        "own_local_ip":      transport_manager._own_ip,
        "active_sessions":   len(hole_puncher._sessions),
        "sessions": {
            sid: {
                "connected":  sess.connected,
                "remote":     sess.remote_addr,
                "candidates": len(sess.local_cands),
            }
            for sid, sess in hole_puncher._sessions.items()
        },
    }


@router.post("/nat/refresh-stun")
async def refresh_stun(u: User = Depends(get_current_user)):
    """Принудительно обновить внешний IP через STUN."""
    result = await StunClient.discover_external()
    if result:
        transport_manager._external_ip, transport_manager._external_port = result
        return {"ok": True, "external_ip": result[0], "external_port": result[1]}
    raise HTTPException(503, "STUN серверы недоступны")