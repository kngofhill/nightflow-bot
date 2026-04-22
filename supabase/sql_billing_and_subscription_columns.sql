-- =============================================================================
-- Nightflow — billing / Telegram Stars (paste into Supabase SQL editor)
-- Idempotent: safe to run on an existing database (ADD COLUMN IF NOT EXISTS).
-- =============================================================================

-- Pro trial, paid Pro window, last payment time
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pro_expires_at TIMESTAMPTZ;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_pro_payment_at TIMESTAMPTZ;

-- Backfill trial for old rows
UPDATE users
SET trial_started_at = COALESCE(trial_started_at, created_at, NOW())
WHERE trial_started_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_pro_expires ON users(pro_expires_at)
    WHERE pro_expires_at IS NOT NULL;

-- Refunds (refundStarPayment) + optional subscription id
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS telegram_payment_charge_id TEXT;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS telegram_subscription_id TEXT;

-- Recurring subscription flags (cancel / status in app and bot)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_cancelled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_active BOOLEAN NOT NULL DEFAULT true;

-- From SuccessfulPayment.is_recurring: false = one-time XTR (editUserStarSubscription N/A)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_payment_is_recurring BOOLEAN;

COMMENT ON COLUMN users.telegram_payment_charge_id IS 'Last successful_payment.telegram_payment_charge_id (XTR / Stars)';
COMMENT ON COLUMN users.telegram_subscription_id IS 'Optional Telegram subscription id if distinct from last charge id';
COMMENT ON COLUMN users.subscription_cancelled IS 'User cancelled auto-renewal; Pro valid until pro_expires_at';
COMMENT ON COLUMN users.subscription_active IS 'False when cancelled in Telegram or after full refund';
COMMENT ON COLUMN users.last_payment_is_recurring IS 'From SuccessfulPayment.is_recurring; false = one-time invoice';
