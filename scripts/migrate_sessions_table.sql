-- SQL migration: 合并会话表，移除 session_tracking，仅保留 sessions，并补全 http_session_id 字段
-- 1. 为 sessions 表添加 http_session_id 字段（如已存在可跳过）
ALTER TABLE sessions ADD COLUMN http_session_id VARCHAR(64);

-- 2. 可选：将 session_tracking 中 http_session_id 数据同步到 sessions（如有需要）
-- UPDATE sessions SET http_session_id = (
--   SELECT http_session_id FROM session_tracking WHERE session_tracking.session_id = sessions.id
-- ) WHERE EXISTS (
--   SELECT 1 FROM session_tracking WHERE session_tracking.session_id = sessions.id
-- );

-- 3. 删除 session_tracking 表
DROP TABLE IF EXISTS session_tracking;

-- 4. 可选：如有 session_name 需求，建议用 id 字段代替，无需迁移

-- 5. 完成
