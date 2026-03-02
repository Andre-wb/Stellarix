"""Управление комнатами."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.security.auth_jwt import get_current_user
from app.peer.connection_manager import manager
from app.database import get_db
from app.models import User
from app.models_rooms import Room, RoomMember, RoomRole
from app.utilites.utils import generative_invite_code
from app.security.crypto import generate_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class RoomCreate(BaseModel):
    name:        str  = Field(..., min_length=1, max_length=100)
    description: str  = Field("", max_length=500)
    is_private:  bool = False


def _dict(r: Room) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "is_private": r.is_private, "invite_code": r.invite_code,
        "member_count": r.member_count(),
        "online_count": len(manager.get_online_users(r.id)),
        "created_at": r.created_at.isoformat(),
    }


def _require_member(room_id: int, user_id: int, db: Session) -> RoomMember:
    m = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == user_id,
        RoomMember.is_banned == False,
        ).first()
    if not m:
        raise HTTPException(403, "Вы не участник этой комнаты")
    return m


@router.post("", status_code=201)
async def create_room(body: RoomCreate, u: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    r = Room(
        name=body.name, description=body.description,
        creator_id=u.id, is_private=body.is_private,
        invite_code=generative_invite_code(8), max_members=200,
        room_key=generate_key(),
    )
    db.add(r); db.flush()
    db.add(RoomMember(room_id=r.id, user_id=u.id, role=RoomRole.OWNER))
    db.commit(); db.refresh(r)
    return JSONResponse(status_code=201, content=_dict(r))


@router.get("/my")
async def my_rooms(u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = [m.room_id for m in db.query(RoomMember).filter(
        RoomMember.user_id == u.id, RoomMember.is_banned == False).all()]
    rooms = db.query(Room).filter(Room.id.in_(ids)).all()
    return {"rooms": [_dict(r) for r in rooms]}


@router.get("/public")
async def public_rooms(db: Session = Depends(get_db)):
    rooms = (db.query(Room).filter(Room.is_private == False)
             .order_by(Room.created_at.desc()).limit(50).all())
    return {"rooms": [_dict(r) for r in rooms]}


@router.post("/join/{invite_code}")
async def join_room(invite_code: str, u: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    r = db.query(Room).filter(Room.invite_code == invite_code.upper()).first()
    if not r:
        raise HTTPException(404, "Комната не найдена")
    existing = db.query(RoomMember).filter(
        RoomMember.room_id == r.id, RoomMember.user_id == u.id).first()
    if existing:
        if existing.is_banned:
            raise HTTPException(403, "Вы заблокированы")
        return {"joined": False, "room": _dict(r)}
    if r.is_full():
        raise HTTPException(409, "Комната заполнена")
    db.add(RoomMember(room_id=r.id, user_id=u.id, role=RoomRole.MEMBER))
    db.commit()
    return {"joined": True, "room": _dict(r)}


@router.delete("/{room_id}/leave")
async def leave_room(room_id: int, u: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    m = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == u.id).first()
    if not m:
        raise HTTPException(404)
    r = db.query(Room).filter(Room.id == room_id).first()
    db.delete(m)
    if m.role == RoomRole.OWNER and r and r.member_count() <= 1:
        db.delete(r); db.commit()
        return {"left": True, "room_deleted": True}
    db.commit()
    return {"left": True, "room_deleted": False}


@router.get("/{room_id}/members")
async def members(room_id: int, u: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    _require_member(room_id, u.id, db)
    all_m = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
    return {"members": [{
        "user_id": m.user_id,
        "username": m.user.username if m.user else "—",
        "display_name": m.user.display_name if m.user else "—",
        "avatar_emoji": m.user.avatar_emoji if m.user else "👤",
        "role": m.role.value,
        "is_online": manager.is_online(room_id, m.user_id),
        "x25519_pubkey": m.user.x25519_public_key if m.user else None,
    } for m in all_m]}


@router.get("/{room_id}")
async def get_room(room_id: int, u: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    r = db.query(Room).filter(Room.id == room_id).first()
    if not r:
        raise HTTPException(404)
    _require_member(room_id, u.id, db)
    return _dict(r)


@router.post("/{room_id}/kick/{target_id}")
async def kick(room_id: int, target_id: int, u: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    actor = _require_member(room_id, u.id, db)
    if actor.role not in (RoomRole.ADMIN, RoomRole.OWNER):
        raise HTTPException(403, "Недостаточно прав")
    t = db.query(RoomMember).filter(
        RoomMember.room_id == room_id, RoomMember.user_id == target_id).first()
    if not t or t.role == RoomRole.OWNER:
        raise HTTPException(403)
    t.is_banned = True; db.commit()
    await manager.send_to_user(room_id, target_id, {"type": "kicked"})
    return {"ok": True}


@router.delete("/{room_id}")
async def delete_room(room_id: int, u: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    m = _require_member(room_id, u.id, db)
    if m.role != RoomRole.OWNER:
        raise HTTPException(403, "Только владелец")
    r = db.query(Room).filter(Room.id == room_id).first()
    if not r:
        raise HTTPException(404)
    await manager.broadcast_to_room(room_id, {"type": "room_deleted"})
    db.delete(r); db.commit()
    return {"ok": True}