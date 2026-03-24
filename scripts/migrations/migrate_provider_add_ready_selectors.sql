-- migrate_provider_add_ready_selectors.sql

ALTER TABLE provider_configs
ADD COLUMN ready_selectors_json TEXT NULL;
