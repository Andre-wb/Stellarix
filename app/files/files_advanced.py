"""
Advanced File Features — distributed storage, media preview, gallery,
file search, auto-compression presets.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import Config
from app.database import get_db
from app.models import User
from app.models_rooms import FileTransfer, Message, Room, RoomMember
from app.security.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files-advanced"])


# ══════════════════════════════════════════════════════════════════════════════
# 1. Distributed Storage (IPFS-style chunk distribution)
# ══════════════════════════════════════════════════════════════════════════════

class DistributedChunk(BaseModel):
    chunk_hash: str
    chunk_index: int
    size: int
    node_ip: str
    node_port: int

class DistributedFileInfo(BaseModel):
    file_hash: str
    filename: str
    total_size: int
    chunk_count: int
    chunks: list[DistributedChunk] = []

# In-memory: file_hash -> {chunks: [{hash, index, size, nodes: [ip:port]}]}
_distributed_index: dict[str, dict] = {}


@router.post("/distributed/register")
async def register_distributed_file(body: DistributedFileInfo,
                                    u: User = Depends(get_current_user),
                                    db: Session = Depends(get_db)):
    """Register a file distributed across multiple nodes (IPFS-style).

    Each chunk is stored on a different node. Client uploads chunks to
    individual nodes, then registers the file map here.
    """
    _distributed_index[body.file_hash] = {
        "filename": body.filename,
        "total_size": body.total_size,
        "chunk_count": body.chunk_count,
        "chunks": [c.model_dump() for c in body.chunks],
        "uploader_id": u.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"ok": True, "file_hash": body.file_hash}


@router.get("/distributed/list")
async def list_distributed_files(u: User = Depends(get_current_user)):
    """List all distributed files on this node."""
    files = []
    for fhash, info in _distributed_index.items():
        files.append({
            "file_hash": fhash,
            "filename": info["filename"],
            "total_size": info["total_size"],
            "chunk_count": info["chunk_count"],
            "created_at": info["created_at"],
        })
    return {"files": files}


@router.get("/distributed/{file_hash}")
async def get_distributed_file(file_hash: str, u: User = Depends(get_current_user)):
    """Get chunk locations for a distributed file."""
    info = _distributed_index.get(file_hash)
    if not info:
        raise HTTPException(404, "Distributed file not found")
    return info


# ══════════════════════════════════════════════════════════════════════════════
# 2. Media Preview (in-browser preview without download)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/preview/{room_id}/{file_id}")
async def media_preview(room_id: int, file_id: int,
                        u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get preview metadata for a file (supports video, audio, documents).

    Returns information needed to render an in-browser preview:
    - Video: poster frame URL, duration, resolution
    - Audio: waveform data, duration
    - Image: thumbnail URL, dimensions
    - Document: page count, preview pages
    """
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
        RoomMember.is_banned == False,
    ).first()
    if not member:
        raise HTTPException(403, "Not a member")

    ft = db.query(FileTransfer).filter(FileTransfer.id == file_id).first()
    if not ft:
        raise HTTPException(404, "File not found")

    mime = ft.mime_type or ""
    preview = {
        "file_id": ft.id,
        "filename": ft.original_name,
        "size": ft.size_bytes,
        "mime_type": mime,
        "download_url": f"/uploads/{ft.stored_name}" if ft.stored_name else None,
    }

    if mime.startswith("image/"):
        preview["type"] = "image"
        preview["thumbnail_url"] = preview["download_url"]
        preview["preview_available"] = True
    elif mime.startswith("video/"):
        preview["type"] = "video"
        preview["stream_url"] = preview["download_url"]
        preview["preview_available"] = True
        preview["controls"] = True
    elif mime.startswith("audio/"):
        preview["type"] = "audio"
        preview["stream_url"] = preview["download_url"]
        preview["preview_available"] = True
    elif mime == "application/pdf":
        preview["type"] = "pdf"
        preview["preview_available"] = True
        preview["viewer_url"] = f"/api/files/viewer/{file_id}"
    else:
        preview["type"] = "file"
        preview["preview_available"] = False

    return preview


# ══════════════════════════════════════════════════════════════════════════════
# 3. Image Gallery (grouped photos, albums)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/gallery/{room_id}")
async def room_gallery(room_id: int, page: int = Query(default=1, ge=1),
                       per_page: int = Query(default=50, le=200),
                       media_type: str = Query(default="all"),
                       u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get media gallery for a room — images, videos, files grouped.

    Args:
        media_type: "all", "images", "videos", "audio", "documents"
    """
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
    ).first()
    if not member:
        raise HTTPException(403, "Not a member")

    query = db.query(FileTransfer).filter(FileTransfer.room_id == room_id)

    if media_type == "images":
        query = query.filter(FileTransfer.mime_type.like("image/%"))
    elif media_type == "videos":
        query = query.filter(FileTransfer.mime_type.like("video/%"))
    elif media_type == "audio":
        query = query.filter(FileTransfer.mime_type.like("audio/%"))
    elif media_type == "documents":
        query = query.filter(
            ~FileTransfer.mime_type.like("image/%"),
            ~FileTransfer.mime_type.like("video/%"),
            ~FileTransfer.mime_type.like("audio/%"),
        )

    total = query.count()
    files = query.order_by(FileTransfer.created_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return {
        "media": [
            {
                "id": f.id,
                "filename": f.original_name,
                "mime_type": f.mime_type,
                "size": f.size_bytes,
                "url": f"/uploads/{f.stored_name}" if f.stored_name else None,
                "uploader_id": f.uploader_id,
                "created_at": f.created_at.isoformat() if f.created_at else "",
            }
            for f in files
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. File Search
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/search/{room_id}")
async def search_files(room_id: int,
                       q: str = Query(default="", max_length=100),
                       file_type: str = Query(default=""),
                       sender_id: int = Query(default=0),
                       u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Search files in a room by name, type, or sender.

    Args:
        q: Search query (filename)
        file_type: Filter by MIME type prefix ("image", "video", "audio", "application/pdf")
        sender_id: Filter by uploader
    """
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
    ).first()
    if not member:
        raise HTTPException(403, "Not a member")

    query = db.query(FileTransfer).filter(FileTransfer.room_id == room_id)

    if q:
        query = query.filter(FileTransfer.original_name.ilike(f"%{q}%"))
    if file_type:
        query = query.filter(FileTransfer.mime_type.like(f"{file_type}%"))
    if sender_id:
        query = query.filter(FileTransfer.uploader_id == sender_id)

    files = query.order_by(FileTransfer.created_at.desc()).limit(50).all()

    return {
        "results": [
            {
                "id": f.id,
                "filename": f.original_name,
                "mime_type": f.mime_type,
                "size": f.size_bytes,
                "url": f"/uploads/{f.stored_name}" if f.stored_name else None,
                "uploader_id": f.uploader_id,
                "download_count": f.download_count,
                "created_at": f.created_at.isoformat() if f.created_at else "",
            }
            for f in files
        ],
        "count": len(files),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. Auto-Compression Presets
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/compression-presets")
async def compression_presets():
    """Return available compression presets for client-side media processing.

    Client applies these before upload to save bandwidth.
    """
    return {
        "presets": {
            "original": {
                "label": "Original Quality",
                "image_quality": 100,
                "max_dimension": None,
                "video_bitrate": None,
                "description": "No compression, full quality",
            },
            "high": {
                "label": "High Quality",
                "image_quality": 85,
                "max_dimension": 2560,
                "video_bitrate": 4000000,
                "video_resolution": "1080p",
                "description": "Slight compression, nearly indistinguishable",
            },
            "medium": {
                "label": "Medium Quality",
                "image_quality": 70,
                "max_dimension": 1920,
                "video_bitrate": 2000000,
                "video_resolution": "720p",
                "description": "Good quality, ~50% size reduction",
            },
            "low": {
                "label": "Low Quality",
                "image_quality": 50,
                "max_dimension": 1280,
                "video_bitrate": 800000,
                "video_resolution": "480p",
                "description": "Smaller files, visible quality reduction",
            },
            "data_saver": {
                "label": "Data Saver",
                "image_quality": 30,
                "max_dimension": 800,
                "video_bitrate": 300000,
                "video_resolution": "360p",
                "description": "Minimum size, for slow connections",
            },
        },
        "max_file_size_mb": Config.MAX_FILE_MB,
        "supported_formats": {
            "images": ["jpeg", "png", "webp", "gif"],
            "video": ["mp4", "webm"],
            "audio": ["mp3", "ogg", "wav", "m4a"],
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# 6. File Stats
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats/{room_id}")
async def file_stats(room_id: int, u: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Get file storage statistics for a room."""
    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id,
    ).first()
    if not member:
        raise HTTPException(403, "Not a member")

    total_files = db.query(func.count(FileTransfer.id)).filter(
        FileTransfer.room_id == room_id
    ).scalar() or 0

    total_size = db.query(func.sum(FileTransfer.size_bytes)).filter(
        FileTransfer.room_id == room_id
    ).scalar() or 0

    # Extract media type prefix (e.g., "image" from "image/jpeg")
    # Use split_part for PostgreSQL, substr+instr for SQLite
    from app.database import engine as _engine
    _is_pg = 'postgresql' in str(_engine.url)
    if _is_pg:
        type_expr = func.split_part(FileTransfer.mime_type, '/', 1)
    else:
        type_expr = func.substr(FileTransfer.mime_type, 1, func.instr(FileTransfer.mime_type, "/") - 1)

    by_type = db.query(
        type_expr,
        func.count(FileTransfer.id),
        func.sum(FileTransfer.size_bytes),
    ).filter(FileTransfer.room_id == room_id).group_by(
        type_expr
    ).all()

    return {
        "total_files": total_files,
        "total_size_bytes": total_size,
        "total_size_human": _human_size(total_size),
        "by_type": {
            (t or "other"): {"count": c, "size_bytes": s or 0, "size_human": _human_size(s or 0)}
            for t, c, s in by_type
        },
    }


def _human_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"
