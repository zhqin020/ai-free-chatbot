-- migrate_provider_configs_add_priority.sql
-- 为 provider_configs 表增加 priority 字段，默认值 100
ALTER TABLE provider_configs ADD COLUMN priority INTEGER NOT NULL DEFAULT 100;
