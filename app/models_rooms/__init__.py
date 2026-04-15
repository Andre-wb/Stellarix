"""
app/models_rooms — Модели комнат, сообщений, файлов и распределённых ключей.

Разбит на подмодули. Все классы реэкспортируются здесь для обратной совместимости:
    from app.models_rooms import Room, RoomMember, Message, ...
"""
from app.models_rooms.enums import RoomRole, MessageType
from app.models_rooms.spaces import Space, SpaceMember, SpaceCategory
from app.models_rooms.rooms import Room, RoomMember
from app.models_rooms.encryption import EncryptedRoomKey, PendingKeyRequest, PendingNotification, SealedKeyPackage
from app.models_rooms.messages import Message, FileTransfer, MessageReaction, MessageEditHistory
from app.models_rooms.collections import RoomTask, SavedMessage
from app.models_rooms.stickers import StickerPack, Sticker, UserFavoritePack, SavedGif
from app.models_rooms.discussions import Topic, ForumThread
from app.models_rooms.permissions import Permission, PermissionFlags, AutoModRule
from app.models_rooms.analytics import (
    PostView, PostReaction, ChannelMonetization, ChannelSubscription,
    ChannelDonation, UserSlowmode,
)
from app.models_rooms.admin import AuditLog, SpaceEmoji
from app.models_rooms.federation import PersistedFederatedRoom, Story, StoryKeyEnvelope
from app.models_rooms.feeds import ChannelFeed

__all__ = [
    # enums
    "RoomRole", "MessageType",
    # spaces
    "Space", "SpaceMember", "SpaceCategory",
    # rooms
    "Room", "RoomMember",
    # encryption
    "EncryptedRoomKey", "PendingKeyRequest", "PendingNotification", "SealedKeyPackage",
    # messages
    "Message", "FileTransfer", "MessageReaction", "MessageEditHistory",
    # collections
    "RoomTask", "SavedMessage",
    # stickers
    "StickerPack", "Sticker", "UserFavoritePack", "SavedGif",
    # discussions
    "Topic", "ForumThread",
    # permissions
    "Permission", "PermissionFlags", "AutoModRule",
    # analytics
    "PostView", "PostReaction", "ChannelMonetization", "ChannelSubscription",
    "ChannelDonation", "UserSlowmode",
    # admin
    "AuditLog", "SpaceEmoji",
    # federation
    "PersistedFederatedRoom", "Story", "StoryKeyEnvelope",
    # feeds
    "ChannelFeed",
]
