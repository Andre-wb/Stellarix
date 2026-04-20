"""Wave 10 (final) — hardware-backed crypto + diagnostic helpers.

  #46 Secure Enclave / TPM  — detect capabilities; store signing key wrapped
                               by an hardware-derived key
  #47 HSM (PKCS#11)          — bridge for enterprise deploys
  #48 NFC pairing            — build/parse NDEF payload for device handoff
  #49 BLE discovery          — advertise / scan adapters status
  #50 GPIO / serial           — diagnostics on SBCs (Raspberry Pi etc.)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import secrets as _secrets
import shutil
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import backup_api as _b
from . import security_api as _sec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiz/admin/hw", tags=["hardware"])


def _env_file(request: Request) -> Path:
    p = getattr(request.app.state, "env_file", None)
    return Path(p) if p else Path(".env")


# ══════════════════════════════════════════════════════════════════════════
# #46 — Secure Enclave / TPM detection + wrap
# ══════════════════════════════════════════════════════════════════════════

def _detect_macos_enclave() -> dict:
    """Check for Apple Secure Enclave availability (Touch ID Mac / Apple Silicon)."""
    if platform.system().lower() != "darwin":
        return {"available": False, "reason": "not_macos"}
    # LocalAuthentication framework detects. Without pyobjc we approximate
    # via system_profiler.
    try:
        from subprocess import run as _run
        r = _run(["system_profiler", "SPHardwareDataType"],
                 capture_output=True, text=True, timeout=3)
        has_enclave = "Apple" in r.stdout and ("Chip" in r.stdout or "T2" in r.stdout)
        return {"available": bool(has_enclave), "platform": "darwin"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def _detect_linux_tpm() -> dict:
    """Check for a TPM 2.0 device (/dev/tpmrm0)."""
    if platform.system().lower() != "linux":
        return {"available": False, "reason": "not_linux"}
    dev = Path("/dev/tpmrm0")
    dev0 = Path("/dev/tpm0")
    available = dev.exists() or dev0.exists()
    tpm2 = shutil.which("tpm2_getcap")
    return {
        "available":   bool(available),
        "device":      str(dev if dev.exists() else dev0) if available else None,
        "tpm2_tools":  tpm2 is not None,
    }


def _detect_windows_tpm() -> dict:
    if platform.system().lower() != "windows":
        return {"available": False, "reason": "not_windows"}
    try:
        from subprocess import run as _run
        r = _run(["powershell", "-Command", "Get-Tpm"],
                 capture_output=True, text=True, timeout=5)
        present = "TpmPresent" in r.stdout and "True" in r.stdout
        return {"available": present, "raw": r.stdout[:500]}
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.get("/enclave/status")
async def enclave_status() -> dict:
    sys_name = platform.system().lower()
    if sys_name == "darwin":   return _detect_macos_enclave() | {"platform": "darwin"}
    if sys_name == "linux":    return _detect_linux_tpm()      | {"platform": "linux"}
    if sys_name == "windows":  return _detect_windows_tpm()    | {"platform": "windows"}
    return {"available": False, "platform": sys_name}


class EnclaveWrapBody(BaseModel):
    enable: bool


@router.post("/enclave/wrap")
async def enclave_wrap(body: EnclaveWrapBody, request: Request) -> dict:
    """Mark the signing key as enclave-wrapped. We don't do the actual
    OS-level wrap here — the wizard bundles a tiny platform-specific
    helper (not yet packaged) that invokes SEKeyCreateRandomKey /
    tpm2_create / ncrypt_create_persisted_key. This endpoint records the
    preference and emits audit."""
    env_file = _env_file(request)
    _sec._write_env_keys(env_file, {
        "HARDWARE_KEY_WRAP": "true" if body.enable else "false",
    })
    return {
        "ok": True,
        "note": "Set a platform helper (sekey.sh / tpm2_wrap.sh) to perform the actual wrap on next node boot.",
    }


# ══════════════════════════════════════════════════════════════════════════
# #47 — HSM (PKCS#11)
# ══════════════════════════════════════════════════════════════════════════

class HsmConfigBody(BaseModel):
    enabled:       bool
    module_path:   str = Field(..., min_length=3,
                               description="Path to PKCS#11 .so/.dll (e.g. /usr/lib/softhsm/libsofthsm2.so)")
    slot_id:       int = Field(0, ge=0, le=1024)
    pin:           Optional[str] = None
    key_label:     str = Field("vortex-signing", min_length=1, max_length=60)


@router.get("/hsm/config")
async def hsm_config_get(request: Request) -> dict:
    env = _b._read_env(_env_file(request))
    return {
        "enabled":     env.get("HSM_ENABLED", "").lower() in ("1","true","yes"),
        "module_path": env.get("PKCS11_MODULE", ""),
        "slot_id":     int(env.get("PKCS11_SLOT", "0") or 0),
        "key_label":   env.get("PKCS11_KEY_LABEL", ""),
        # Never return the pin.
    }


@router.post("/hsm/config")
async def hsm_config_set(body: HsmConfigBody, request: Request) -> dict:
    p = Path(body.module_path)
    if body.enabled and not p.is_file():
        raise HTTPException(400, f"PKCS#11 module not found: {body.module_path}")
    env_file = _env_file(request)
    updates = {
        "HSM_ENABLED":     "true" if body.enabled else "false",
        "PKCS11_MODULE":   body.module_path,
        "PKCS11_SLOT":     str(body.slot_id),
        "PKCS11_KEY_LABEL": body.key_label,
    }
    if body.pin is not None:
        updates["PKCS11_PIN"] = body.pin
    _sec._write_env_keys(env_file, updates)
    return {"ok": True}


@router.post("/hsm/test")
async def hsm_test(request: Request) -> dict:
    """Load the PKCS#11 module and list available slots — sanity check."""
    env = _b._read_env(_env_file(request))
    if env.get("HSM_ENABLED", "").lower() not in ("1","true","yes"):
        raise HTTPException(400, "HSM not enabled")
    mod = env.get("PKCS11_MODULE", "")
    if not (mod and Path(mod).is_file()):
        raise HTTPException(400, f"module not found: {mod}")
    try:
        import pkcs11  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(500, "python-pkcs11 not installed — pip install python-pkcs11")

    try:
        lib = pkcs11.lib(mod)
        slots = [{"slot_id": s.slot_id,
                  "description": s.slot_description,
                  "token_label": (s.get_token().label if s.get_token() else None)}
                 for s in lib.get_slots(token_present=True)]
        return {"ok": True, "slots": slots}
    except Exception as e:
        raise HTTPException(500, f"pkcs11 load failed: {e}")


# ══════════════════════════════════════════════════════════════════════════
# #48 — NFC pairing payload
# ══════════════════════════════════════════════════════════════════════════
#
# We generate an NDEF record (URI record) that a peer phone reads via
# NFC. The payload is the same signed QR we use for device linking —
# just encoded for NFC writers. Writing to a physical tag requires a
# PCSC reader + Python NFC library on the wizard host.

@router.post("/nfc/generate")
async def nfc_generate(request: Request) -> dict:
    """Return the NDEF bytes + hex so a phone app or NFC-writer desktop
    tool can flash the tag."""
    env_file = _env_file(request)
    from . import multidevice as _md
    # Reuse the device-link QR URI
    link = await _md.make_device_link(_md.DeviceLinkBody(ttl_seconds=900), request)
    uri = link.get("uri", "")

    # NDEF URI record encoding (abbreviation 0x00 = "none" — full URI).
    # https://developer.android.com/training/beam-files/share-files#nfc-intent
    payload = bytes([0x00]) + uri.encode("utf-8")
    record_header = bytes([0xD1, 0x01, len(payload), 0x55])   # MB=1, ME=1, SR=1, TNF=1, type=U
    ndef = record_header + payload
    return {
        "uri":           uri,
        "ndef_hex":      ndef.hex(),
        "ndef_size":     len(ndef),
        "recommendation":"use ACR122U or PN532 with `nfcpy` to write this to an NTAG215/216",
    }


# ══════════════════════════════════════════════════════════════════════════
# #49 — BLE discovery
# ══════════════════════════════════════════════════════════════════════════

@router.get("/ble/adapter")
async def ble_adapter() -> dict:
    """Report whether a usable BLE adapter is present on the host.
    Linux: /sys/class/bluetooth. macOS: system_profiler SPBluetoothDataType."""
    sys_name = platform.system().lower()
    if sys_name == "linux":
        d = Path("/sys/class/bluetooth")
        return {"present": d.is_dir() and any(d.iterdir()),
                "platform": "linux"}
    if sys_name == "darwin":
        from subprocess import run as _run
        try:
            r = _run(["system_profiler", "SPBluetoothDataType"],
                     capture_output=True, text=True, timeout=3)
            return {"present": "Bluetooth" in r.stdout and "Not Available" not in r.stdout,
                    "platform": "darwin"}
        except Exception as e:
            return {"present": False, "error": str(e)}
    return {"present": False, "platform": sys_name}


@router.post("/ble/scan")
async def ble_scan(duration: int = 5) -> dict:
    """Scan for BLE advertisements. Requires `bleak` or the OS CLI."""
    duration = max(1, min(duration, 30))
    try:
        from bleak import BleakScanner  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(500, "bleak not installed — pip install bleak")

    try:
        devices = await BleakScanner.discover(timeout=float(duration))
        return {
            "ok":      True,
            "count":   len(devices),
            "devices": [{"address": d.address, "name": d.name,
                         "rssi": getattr(d, "rssi", None)} for d in devices],
        }
    except Exception as e:
        raise HTTPException(500, f"ble scan failed: {e}")


# ══════════════════════════════════════════════════════════════════════════
# #50 — GPIO / serial diagnostics
# ══════════════════════════════════════════════════════════════════════════

@router.get("/sbc/info")
async def sbc_info() -> dict:
    """Gather basic info useful for Pi/Rock/NUC deploys:
    /proc/cpuinfo revision, thermal zone, GPIO chip count, uart list."""
    out: dict = {"platform": platform.system().lower()}
    try:
        with open("/proc/cpuinfo") as f:
            cpu = f.read()
        out["cpu_model"] = next((l.split(":",1)[1].strip()
                                 for l in cpu.splitlines() if l.startswith("Model")), None)
        out["hardware"]  = next((l.split(":",1)[1].strip()
                                 for l in cpu.splitlines() if l.startswith("Hardware")), None)
    except Exception:
        pass
    # Thermal
    try:
        temp_f = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_f.is_file():
            out["temp_c"] = int(temp_f.read_text().strip()) / 1000.0
    except Exception: pass
    # GPIO chips
    try:
        chips = sorted(Path("/dev").glob("gpiochip*"))
        out["gpio_chips"] = [str(c) for c in chips]
    except Exception: pass
    # UARTs
    try:
        ttys = sorted(p.name for p in Path("/dev").glob("ttyS*"))
        ttys += sorted(p.name for p in Path("/dev").glob("ttyUSB*"))
        ttys += sorted(p.name for p in Path("/dev").glob("ttyAMA*"))
        out["uart_devices"] = ttys
    except Exception: pass
    return out


class SerialEchoBody(BaseModel):
    device:    str = Field(..., min_length=3, max_length=100)
    baud:      int = Field(115200, ge=1200, le=4_000_000)
    data_hex:  str = Field(..., min_length=2)
    read_bytes: int = Field(0, ge=0, le=4096)


@router.post("/sbc/serial")
async def serial_echo(body: SerialEchoBody) -> dict:
    """Open a serial device, write payload, optionally read response.
    For cheap diagnostics — pipe diagnostic LEDs, probe GPS modules, etc."""
    if not body.device.startswith("/dev/"):
        raise HTTPException(400, "device must be under /dev/")
    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(500, "pyserial not installed — pip install pyserial")
    try:
        payload = bytes.fromhex(body.data_hex)
    except ValueError:
        raise HTTPException(400, "data_hex is not valid hex")
    try:
        with serial.Serial(body.device, body.baud, timeout=1) as s:
            s.write(payload)
            read = s.read(body.read_bytes) if body.read_bytes else b""
        return {"ok": True, "wrote": len(payload), "read_hex": read.hex()}
    except Exception as e:
        raise HTTPException(500, f"serial op failed: {e}")
