package sol.vortexx.android.db.entities

import androidx.room.Entity
import androidx.room.Fts4

/**
 * Full-text search index over [MessageEntity.plaintext]. Populated by a
 * trigger-equivalent (manual upsert from ChatEngine) since Room doesn't
 * do implicit FTS mirroring across non-FTS tables.
 *
 * Wave-parity note: the web client uses per-room encrypted-at-rest SQLite
 * FTS; here we leverage Android's built-in FTS4 and rely on the DB file
 * itself being stored under Android's user-data dir (full-disk encryption
 * on any modern device).
 */
@Fts4
@Entity(tableName = "messages_fts")
data class MessageFts(
    val rowid: Long,           // mirrors MessageEntity.id
    val plaintext: String,
)
