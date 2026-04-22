-- Whether the last successful Stars payment was a Telegram recurring subscription (True) or one-time (False).
-- editUserStarSubscription only works for recurring; one-time uses DB-only "cancel".
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_payment_is_recurring BOOLEAN;

COMMENT ON COLUMN users.last_payment_is_recurring IS 'From SuccessfulPayment.is_recurring; false when bot fell back to one-time XTR invoice';
