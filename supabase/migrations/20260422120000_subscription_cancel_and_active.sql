-- Recurring Stars subscription: cancel at period end, refund handling
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_cancelled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS telegram_subscription_id TEXT;

COMMENT ON COLUMN users.subscription_cancelled IS 'User cancelled auto-renewal; Pro valid until pro_expires_at';
COMMENT ON COLUMN users.subscription_active IS 'False when cancelled in Telegram or after full refund';
COMMENT ON COLUMN users.telegram_subscription_id IS 'Optional: Telegram subscription reference if distinct from last charge id';
