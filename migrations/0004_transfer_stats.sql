CREATE TABLE IF NOT EXISTS transfer_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    ok BOOLEAN NOT NULL,
    bytes BIGINT,
    duration_ms BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS transfer_stats_user_created_idx ON transfer_stats (user_id, created_at DESC);
