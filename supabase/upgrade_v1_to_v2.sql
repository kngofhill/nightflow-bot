-- Run in Supabase SQL editor if you already deployed the older schema from the handoff.
-- Safe to re-run: uses IF NOT EXISTS where possible.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- New column on users (mini-app notification toggles)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{}'::jsonb;

-- Optional: rotating pattern anchor date (ignore if column not needed)
ALTER TABLE rotating_patterns
    ADD COLUMN IF NOT EXISTS pattern_start_date DATE;

-- End-of-shift slider data (POST /api/v1/summaries later)
CREATE TABLE IF NOT EXISTS shift_summaries (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_date DATE NOT NULL,
    energy SMALLINT CHECK (energy IS NULL OR (energy >= 1 AND energy <= 4)),
    sleep_quality SMALLINT CHECK (sleep_quality IS NULL OR (sleep_quality >= 1 AND sleep_quality <= 4)),
    responses JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, local_date)
);

CREATE INDEX IF NOT EXISTS idx_shift_summaries_user_date ON shift_summaries(user_id, local_date DESC);

-- Helpful composite index for the bot scheduler
CREATE INDEX IF NOT EXISTS idx_notifications_user_time_pending
    ON notifications(user_id, scheduled_time)
    WHERE sent = false;

-- Weekly report lookups
CREATE INDEX IF NOT EXISTS idx_weekly_reports_user ON weekly_reports(user_id);

CREATE INDEX IF NOT EXISTS idx_rotating_patterns_user ON rotating_patterns(user_id) WHERE active = true;
