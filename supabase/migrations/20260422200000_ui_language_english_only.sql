-- English-only UI. Backfill and narrow constraint (was en/ru/uz).
UPDATE users SET ui_language = 'en' WHERE ui_language IN ('ru', 'uz');

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_ui_language_check;
ALTER TABLE users ADD CONSTRAINT users_ui_language_check
    CHECK (ui_language IS NULL OR ui_language = 'en');

COMMENT ON COLUMN users.ui_language IS 'App UI language: en only. NULL = not yet set.';
