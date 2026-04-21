-- Telegram Stars subscription + 14-day Pro trial
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pro_expires_at TIMESTAMPTZ;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_pro_payment_at TIMESTAMPTZ;

UPDATE users
SET trial_started_at = COALESCE(trial_started_at, created_at, NOW())
WHERE trial_started_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_pro_expires ON users(pro_expires_at)
    WHERE pro_expires_at IS NOT NULL;
