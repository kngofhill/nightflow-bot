-- Last successful Telegram Stars payment (for API refunds via refundStarPayment)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS telegram_payment_charge_id TEXT;

COMMENT ON COLUMN users.telegram_payment_charge_id IS 'Most recent successful_payment.telegram_payment_charge_id (XTR)';
