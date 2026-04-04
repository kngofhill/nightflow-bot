-- Performance indexes for NightFlowBot
-- Run this in Supabase SQL Editor

-- Users table indexes
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_notification_enabled ON users(notification_enabled) WHERE notification_enabled = true;
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active DESC);

-- Constant schedules indexes
CREATE INDEX IF NOT EXISTS idx_constant_schedules_user_active ON constant_schedules(user_id, active) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_constant_schedules_updated_at ON constant_schedules(updated_at DESC);

-- Daily schedules indexes
CREATE INDEX IF NOT EXISTS idx_daily_schedules_user_date ON daily_schedules(user_id, date);
CREATE INDEX IF NOT EXISTS idx_daily_schedules_date ON daily_schedules(date);
CREATE INDEX IF NOT EXISTS idx_daily_schedules_shift_type ON daily_schedules(shift_type) WHERE shift_type = 'off';

-- Rotating patterns indexes
CREATE INDEX IF NOT EXISTS idx_rotating_patterns_user_active ON rotating_patterns(user_id) WHERE pattern_start_date <= CURRENT_DATE;

-- Shift summaries indexes
CREATE INDEX IF NOT EXISTS idx_shift_summaries_user_date ON shift_summaries(user_id, local_date DESC);
CREATE INDEX IF NOT EXISTS idx_shift_summaries_date_range ON shift_summaries(local_date) WHERE local_date >= CURRENT_DATE - INTERVAL '30 days';

-- Notifications indexes
CREATE INDEX IF NOT EXISTS idx_notifications_user_sent ON notifications(user_id, sent) WHERE sent = false;
CREATE INDEX IF NOT EXISTS idx_notifications_type_time ON notifications(type, scheduled_time);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_daily_schedules_user_date_shift ON daily_schedules(user_id, date, shift_type);
CREATE INDEX IF NOT EXISTS idx_shift_summaries_user_date_energy ON shift_summaries(user_id, local_date, energy);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update updated_at
CREATE TRIGGER update_constant_schedules_updated_at 
    BEFORE UPDATE ON constant_schedules 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Analyze tables to update statistics
ANALYZE users;
ANALYZE constant_schedules;
ANALYZE daily_schedules;
ANALYZE rotating_patterns;
ANALYZE shift_summaries;
ANALYZE notifications;
