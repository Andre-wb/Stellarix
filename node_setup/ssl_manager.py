from __future__ import annotations
import datetime
import ipaddress
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

class SSLResult(NamedTuple):
    ok: bool
    cert: str
    key: str
    ca: str
    message: str
    trusted: bool

def _local_ips() -> list[str]:
    """Собирает все IP-адреса этой машины."""
    ips = {"127.0.0.1", "::1"}
    try:
        hostname = socket.gethostname()
        ips.add(socket.gethostbyname(hostname))
    except Exception:
        pass
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for family in (netifaces.AF_INET, netifaces.AF_INET6):
                for addr in addrs.get(family, []):
                    ips.add(addr["addr"].split("%")[0])
    except ImportError:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for target in ("192.168.1.1", "10.0.0.1", "8.8.8.8"):
                try:
                    s.connect((target, 80))
                    ips.add(s.getsockname()[0])
                    break
                except Exception:
                    pass
            s.close()
        except Exception:
            pass
    return sorted(ips)


def _get_system() -> str:
    """Возвращает строку системы: 'windows' | 'macos' | 'debian' | 'rhel' | 'arch' | 'linux'."""
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    if s == "darwin":
        return "macos"
    if Path("/etc/debian_version").exists():
        return "debian"
    if Path("/etc/redhat-release").exists() or Path("/etc/fedora-release").exists():
        return "rhel"
    if Path("/etc/arch-release").exists():
        return "arch"
    return "linux"

def generate_self_signed(
        cert_dir: Path,
        hostname: str = "",
        org_name: str = "Vortex Node",
        days: int = 825,
        install_ca: bool = True,
) -> SSLResult:
    """
    Генерирует самоподписанный CA + сертификат сервера.
    Добавляет все локальные IP как SAN записи.

    Возвращает SSLResult с путями к файлам.
    """

    cert_dir.mkdir(parents=True, exist_ok=True)
    backend  = default_backend()
    hostname = hostname or socket.gethostname()
    now      = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(
        public_exponent=65537, key_size=4096, backend=backend
    )
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME,             "XX"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME,        f"{org_name} CA"),
        x509.NameAttribute(NameOID.COMMON_NAME,              f"{org_name} Root CA"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 лет для CA
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True,
            content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(ca_key, hashes.SHA256(), backend)
    )
    srv_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=backend
    )
    san_list: list = [
        x509.DNSName("localhost"),
        x509.DNSName(hostname),
        x509.DNSName(hostname + ".local"),
    ]
    for ip_str in _local_ips():
        try:
            san_list.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
        except ValueError:
            pass

    srv_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME,             "XX"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME,        org_name),
        x509.NameAttribute(NameOID.COMMON_NAME,              hostname),
    ])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_encipherment=True, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256(), backend)
    )
    ca_path   = cert_dir / "vortex-ca.crt"
    cert_path = cert_dir / "vortex.crt"
    key_path  = cert_dir / "vortex.key"

    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(srv_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))

    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass

    logger.info(f"SSL: сгенерированы сертификаты в {cert_dir}")
    trusted = False
    if install_ca:
        trusted = install_ca_to_trust_store(ca_path)

    return SSLResult(
        ok=True,
        cert=str(cert_path),
        key=str(key_path),
        ca=str(ca_path),
        message=f"Сертификат создан для: {hostname} + {len(_local_ips())} IP-адресов",
        trusted=trusted,
    )

def install_ca_to_trust_store(ca_path: Path) -> bool:
    """
    Устанавливает CA-сертификат в системное хранилище доверия.
    Требует прав администратора на большинстве систем.

    Возвращает True если успешно.
    """
    system = _get_system()
    try:
        if system == "macos":
            return _install_ca_macos(ca_path)
        elif system == "windows":
            return _install_ca_windows(ca_path)
        elif system == "debian":
            return _install_ca_debian(ca_path)
        elif system in ("rhel", "arch", "linux"):
            return _install_ca_linux_generic(ca_path)
    except Exception as e:
        logger.warning(f"Не удалось установить CA: {e}")
    return False


def _install_ca_macos(ca_path: Path) -> bool:
    result = subprocess.run(
        ["sudo", "security", "add-trusted-cert",
         "-d", "-r", "trustRoot",
         "-k", "/Library/Keychains/System.keychain",
         str(ca_path)],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _install_ca_windows(ca_path: Path) -> bool:
    result = subprocess.run(
        ["certutil", "-addstore", "-f", "ROOT", str(ca_path)],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    return result.returncode == 0


def _install_ca_debian(ca_path: Path) -> bool:
    dest = Path("/usr/local/share/ca-certificates") / ca_path.name
    subprocess.run(["sudo", "cp", str(ca_path), str(dest)], check=True)
    result = subprocess.run(["sudo", "update-ca-certificates"], capture_output=True, text=True)
    return result.returncode == 0


def _install_ca_linux_generic(ca_path: Path) -> bool:
    for dest_dir, update_cmd in [
        ("/etc/pki/ca-trust/source/anchors",    ["sudo", "update-ca-trust", "extract"]),
        ("/etc/ca-certificates/trust-source",   ["sudo", "trust", "extract-compat"]),
        ("/usr/local/share/ca-certificates",    ["sudo", "update-ca-certificates"]),
    ]:
        if Path(dest_dir).exists():
            subprocess.run(["sudo", "cp", str(ca_path), dest_dir], check=True)
            result = subprocess.run(update_cmd, capture_output=True, text=True)
            return result.returncode == 0
    return False


def get_ca_install_instructions(ca_path: Path) -> str:
    """Возвращает инструкции по ручной установке CA для текущей ОС."""
    system = _get_system()
    p = str(ca_path.resolve())
    instructions = {
        "macos":   f"sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain {p}",
        "windows": f"certutil -addstore -f ROOT {p}  (от имени администратора)",
        "debian":  f"sudo cp {p} /usr/local/share/ca-certificates/ && sudo update-ca-certificates",
        "rhel":    f"sudo cp {p} /etc/pki/ca-trust/source/anchors/ && sudo update-ca-trust extract",
        "arch":    f"sudo trust anchor {p}",
        "linux":   f"sudo cp {p} /usr/local/share/ca-certificates/ && sudo update-ca-certificates",
    }
    return instructions.get(system, instructions["linux"])

def generate_with_mkcert(cert_dir: Path, hostname: str = "") -> SSLResult:
    """Использует mkcert если установлен — создаёт браузерно-доверенные сертификаты."""
    mkcert_bin = shutil.which("mkcert")
    if not mkcert_bin:
        return SSLResult(ok=False, cert="", key="", ca="",
                         message="mkcert не найден. Установите: https://github.com/FiloSottile/mkcert",
                         trusted=False)
    cert_dir.mkdir(parents=True, exist_ok=True)
    hostname = hostname or socket.gethostname()
    cert_path = cert_dir / "vortex.crt"
    key_path  = cert_dir / "vortex.key"
    ips       = _local_ips()

    domains = [hostname, "localhost", "127.0.0.1"] + ips

    # Устанавливаем CA
    subprocess.run([mkcert_bin, "-install"], capture_output=True)

    result = subprocess.run(
        [mkcert_bin,
         "-cert-file", str(cert_path),
         "-key-file",  str(key_path),
         *domains],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return SSLResult(ok=False, cert="", key="", ca="",
                         message=f"mkcert ошибка: {result.stderr}",
                         trusted=False)

    ca_path = _get_mkcert_ca_path()
    return SSLResult(
        ok=True, cert=str(cert_path), key=str(key_path), ca=ca_path or "",
        message=f"mkcert: сертификат создан для {len(domains)} хостов/IP",
        trusted=True,
    )


def _get_mkcert_ca_path() -> str:
    mkcert_bin = shutil.which("mkcert")
    if not mkcert_bin:
        return ""
    r = subprocess.run([mkcert_bin, "-CAROOT"], capture_output=True, text=True)
    if r.returncode == 0:
        ca_dir = Path(r.stdout.strip())
        for name in ("rootCA.pem", "rootCA.crt"):
            p = ca_dir / name
            if p.exists():
                return str(p)
    return ""

def generate_letsencrypt(
        cert_dir: Path,
        domain: str,
        email: str,
        port: int = 80,
        staging: bool = False,
) -> SSLResult:
    """
    Получает Let's Encrypt сертификат через certbot.
    Требует: открытый порт 80, домен указывающий на этот IP.
    """
    certbot_bin = shutil.which("certbot") or shutil.which("certbot3")
    if not certbot_bin:
        return SSLResult(ok=False, cert="", key="", ca="",
                         message="certbot не найден. Установите: https://certbot.eff.org/",
                         trusted=False)

    cert_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        certbot_bin, "certonly",
        "--standalone",
        "--non-interactive",
        "--agree-tos",
        f"--email={email}",
        f"--domain={domain}",
        f"--http-01-port={port}",
        f"--config-dir={cert_dir / 'certbot'}",
        f"--work-dir={cert_dir / 'certbot' / 'work'}",
        f"--logs-dir={cert_dir / 'certbot' / 'logs'}",
    ]
    if staging:
        cmd.append("--staging")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return SSLResult(ok=False, cert="", key="", ca="",
                         message=f"certbot ошибка: {result.stderr[:400]}",
                         trusted=False)

    live_dir  = cert_dir / "certbot" / "live" / domain
    cert_path = live_dir / "fullchain.pem"
    key_path  = live_dir / "privkey.pem"

    if not cert_path.exists() or not key_path.exists():
        return SSLResult(ok=False, cert="", key="", ca="",
                         message=f"certbot: файлы не найдены в {live_dir}",
                         trusted=False)

    import shutil as sh
    sh.copy2(cert_path, cert_dir / "vortex.crt")
    sh.copy2(key_path,  cert_dir / "vortex.key")

    return SSLResult(
        ok=True,
        cert=str(cert_dir / "vortex.crt"),
        key=str(cert_dir / "vortex.key"),
        ca="",
        message=f"Let's Encrypt: сертификат для {domain} получен",
        trusted=True,
    )


def use_manual_cert(cert_src: str, key_src: str, cert_dir: Path) -> SSLResult:
    """Копирует существующие файлы сертификата в рабочую директорию."""
    import shutil as sh
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "vortex.crt"
    key_path = cert_dir / "vortex.key"
    try:
        sh.copy2(cert_src, cert_path)
        sh.copy2(key_src, key_path)
        os.chmod(key_path,0o600)
        return SSLResult(ok=True, cert=str(cert_path), key=str(key_path), ca="",
                         message="Сертификат скопирован", trusted=True)
    except Exception as e:
        return SSLResult(ok=False, cert="", key="", ca="",
                         message=f"Ошибка копирования: {e}", trusted=False)

def check_cert_expiry(cert_path: Path) -> dict:
    """Возвращает информацию об истечении срока сертификата."""
    try:
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        now = datetime.datetime.now(datetime.timezone.utc)
        exp = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else \
            cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
        delta = exp - now
        return {
            "valid": delta.days > 0,
            "expires_at": exp.isoformat(),
            "days_left": max(0, delta.days),
            "subject": cert.subject.rfc4514_string(),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}

def detect_available_methods() -> dict[str, bool]:
    return {
        "self_signed": True,
        "mkcert": bool(shutil.which("mkcert")),
        "letsencrypt": bool(shutil.which("certbot") or shutil.which("certbot3")),
        "manual": True,
    }