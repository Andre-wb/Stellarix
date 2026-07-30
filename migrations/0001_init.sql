-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
                                     id TEXT PRIMARY KEY,
                                     username TEXT NOT NULL UNIQUE,
                                     password_hash TEXT NOT NULL,
                                     created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                     last_login_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Таблица чатов
CREATE TABLE IF NOT EXISTS chats (
                                     id TEXT PRIMARY KEY,
                                     owner_id TEXT NOT NULL,
                                     peer_fingerprint TEXT NOT NULL,
                                     created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                     FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(owner_id, peer_fingerprint)
    );

CREATE INDEX IF NOT EXISTS idx_chats_owner_id ON chats(owner_id);

-- Таблица сообщений
CREATE TABLE IF NOT EXISTS messages (
                                        id TEXT PRIMARY KEY,
                                        chat_id TEXT NOT NULL,
                                        outgoing BOOLEAN NOT NULL,
                                        payload_hex TEXT NOT NULL,
                                        sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                        FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
    );

CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);

-- Таблица статистики сессий (бывшая transfer_stats)
CREATE TABLE IF NOT EXISTS transfer_stats (
                                              id TEXT PRIMARY KEY,
                                              user_id TEXT NOT NULL,
                                              kind TEXT NOT NULL,
                                              ok BOOLEAN NOT NULL,
                                              bytes INTEGER,
                                              duration_ms INTEGER,
                                              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

CREATE INDEX IF NOT EXISTS idx_transfer_stats_user_created ON transfer_stats(user_id, created_at DESC);