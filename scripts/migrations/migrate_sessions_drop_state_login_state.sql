-- 删除 sessions 表中的 state 和 login_state 字段（如存在）
ALTER TABLE sessions DROP COLUMN IF EXISTS state;
ALTER TABLE sessions DROP COLUMN IF EXISTS login_state;
-- 如有历史数据依赖请提前备份
