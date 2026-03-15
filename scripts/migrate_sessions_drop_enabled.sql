-- SQL migration: 移除 sessions 表中的 enabled 字段
-- SQLite 不支持直接 DROP COLUMN，需重建表

PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

-- 1. 重命名原表
ALTER TABLE sessions RENAME TO sessions_old;

-- 2. 创建新表（去除 enabled 字段，保留其它字段）
CREATE TABLE sessions (
    id VARCHAR(64) PRIMARY KEY,
    provider VARCHAR(64) NOT NULL,
    chat_url TEXT NOT NULL,
    http_session_id VARCHAR(64),
    priority INTEGER DEFAULT 100 NOT NULL,
    state VARCHAR(32) DEFAULT 'READY' NOT NULL,
    login_state VARCHAR(32) DEFAULT 'unknown' NOT NULL,
    last_seen_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

-- 3. 拷贝数据（不包含 enabled 字段）
INSERT INTO sessions (id, provider, chat_url, http_session_id, priority, state, login_state, last_seen_at, created_at, updated_at)
SELECT id, provider, chat_url, http_session_id, priority, state, login_state, last_seen_at, created_at, updated_at FROM sessions_old;

-- 4. 删除旧表
DROP TABLE sessions_old;

COMMIT;

PRAGMA foreign_keys=on;
