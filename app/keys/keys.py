from fastapi import APIRouter
from app.security.crypto import load_or_create_node_keypair
from app.config import Config

router = APIRouter(prefix="/api/keys", tags=["keys"])

@router.get("/pubkey")
async def get_node_pubkey():
    """Возвращает X25519 публичный ключ этого узла."""
    _, node_pub_raw = load_or_create_node_keypair(Config.KEYS_DIR)
    node_pub = node_pub_raw if isinstance(node_pub_raw, bytes) else bytes(node_pub_raw)
    return {"pubkey_hex": node_pub.hex()}