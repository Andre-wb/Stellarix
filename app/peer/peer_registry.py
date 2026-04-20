"""
app/peer/peer_registry.py — Thin re-export shim.

All logic has been split into sub-modules:
  - peer_models.py      (PeerInfo, PeerRegistry, registry, _main_loop)
  - peer_discovery.py   (start_discovery, UDP helpers/listeners)
  - peer_p2p.py         (P2P send/receive routes)
  - peer_federation.py  (federated-join, multihop-join routes)
  - peer_routes.py      (list_peers, peer_status, invite-qr, etc.)

This file preserves backward-compatible imports:
    from app.peer.peer_registry import router, registry, start_discovery, PeerInfo, PeerRegistry
"""

# Re-export the shared router (routes are registered via side-effect imports below)
from app.peer._router import router  # noqa: F401

# Core models & singleton
from app.peer.peer_models import PeerInfo, PeerRegistry, registry  # noqa: F401

# Discovery entry-point
from app.peer.peer_discovery import start_discovery  # noqa: F401

# Side-effect imports: importing these modules registers their @router routes
import app.peer.peer_routes       # noqa: F401
import app.peer.peer_p2p          # noqa: F401
import app.peer.peer_federation   # noqa: F401
import app.peer.peer_public_keys  # noqa: F401
