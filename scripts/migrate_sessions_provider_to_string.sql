-- SQLite migration: convert sessions.provider from ENUM to VARCHAR
-- 1. Rename old table
ALTER TABLE sessions RENAME TO sessions_old;

-- 2. Create new table with provider as VARCHAR
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    provider VARCHAR(64) NOT NULL,
    chat_url TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    state VARCHAR(32) NOT NULL DEFAULT 'READY',
    login_state VARCHAR(32) NOT NULL DEFAULT 'unknown',
    last_seen_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- 3. Copy data
INSERT INTO sessions
(id, provider, chat_url, enabled, priority, state, login_state, last_seen_at, created_at, updated_at)
SELECT id, provider, chat_url, enabled, priority, state, login_state, last_seen_at, created_at, updated_at
FROM sessions_old;

-- 4. Drop old table
DROP TABLE sessions_old;
