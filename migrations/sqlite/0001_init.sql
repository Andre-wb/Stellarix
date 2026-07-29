-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
                                     id TEXT PRIMARY KEY,
                                     username TEXT UNIQUE NOT NULL,
                                     password_hash TEXT NOT NULL,
                                     created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                     last_login_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Создание таблицы чатов
CREATE TABLE IF NOT EXISTS chats (
                                     id TEXT PRIMARY KEY,
                                     owner_id TEXT NOT NULL,
                                     peer_fingerprint TEXT NOT NULL,
                                     created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                     FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(owner_id, peer_fingerprint)
    );

CREATE INDEX IF NOT EXISTS idx_chats_owner_id ON chats(owner_id);

-- Создание таблицы сообщений
CREATE TABLE IF NOT EXISTS messages (
                                        id TEXT PRIMARY KEY,
                                        chat_id TEXT NOT NULL,
                                        outgoing BOOLEAN NOT NULL,
                                        payload_hex TEXT NOT NULL,
                                        sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                        FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
    );

CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);

-- Создание таблицы статистики сессий
CREATE TABLE IF NOT EXISTS session_stats (
                                             id TEXT PRIMARY KEY,
                                             user_id TEXT NOT NULL,
                                             session_type TEXT NOT NULL,
                                             volume TEXT,
                                             duration TEXT,
                                             speed TEXT,
                                             status TEXT,
                                             ok BOOLEAN,
                                             at INTEGER,
                                             kind TEXT,
                                             bytes INTEGER,
                                             ms INTEGER,
                                             created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                             FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

CREATE INDEX IF NOT EXISTS idx_session_stats_user_id ON session_stats(user_id);