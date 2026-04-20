"""
app/chats/rooms/ — Управление комнатами.

Модули:
  helpers.py  — Общий router, Pydantic-схемы, вспомогательные функции
  crud.py     — CRUD: создание, обновление, удаление, покидание
  members.py  — Участники: список, кик, роли, мут, бан
  keys.py     — Ключи: вступление, предоставление, key-bundle, ротация
  theme.py    — Темы комнат: установка, сброс, принятие DM-тем
"""
from app.chats.rooms.helpers import router, _room_dict  # noqa: F401

# Импорт подмодулей регистрирует @router.* декораторы на общем router
import app.chats.rooms.crud     # noqa: F401
import app.chats.rooms.members  # noqa: F401
import app.chats.rooms.keys         # noqa: F401
import app.chats.rooms.sealed_keys  # noqa: F401
import app.chats.rooms.public_keys  # noqa: F401
import app.chats.rooms.theme        # noqa: F401
