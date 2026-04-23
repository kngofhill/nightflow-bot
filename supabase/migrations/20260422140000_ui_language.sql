-- App + bot interface language: en, ru, uz. NULL = user has not chosen yet (/start shows picker).
ALTER TABLE users ADD COLUMN IF NOT EXISTS ui_language TEXT
    CHECK (ui_language IS NULL OR ui_language IN ('en', 'ru', 'uz'));

COMMENT ON COLUMN users.ui_language IS 'Mini app UI: en, ru, uz. NULL = show language choice on /start.';
