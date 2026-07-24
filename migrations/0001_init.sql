CREATE TABLE IF NOT EXISTS users (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    public_key     TEXT NOT NULL,
    private_key    TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at  TIMESTAMPTZ
);

-- gen_random_uuid() needs pgcrypto on older Postgres (Postgres 13+ has it built in as of PG13,
-- but pgcrypto extension guarantees it on any version).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
