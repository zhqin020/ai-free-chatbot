-- migrate_sessions_add_priority.sql
-- 为 sessions 表增加 priority 字段，默认值 100
ALTER TABLE sessions ADD COLUMN priority INTEGER NOT NULL DEFAULT 100;
