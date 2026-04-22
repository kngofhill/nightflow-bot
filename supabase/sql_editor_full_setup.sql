-- =============================================================================
-- NIGHTFLOW — paste ALL of this into Supabase → SQL Editor → Run
-- Safe if you already dropped your old tables (or empty project).
-- If you get "does not exist" on DROPs, ignore — keep running to the end.
-- =============================================================================

-- --- tear down (only objects this app created) ---
DROP VIEW IF EXISTS active_users_with_schedules CASCADE;
DROP VIEW IF EXISTS todays_notifications CASCADE;

DROP TABLE IF EXISTS shift_details CASCADE;
DROP TABLE IF EXISTS shift_summaries CASCADE;
DROP TABLE IF EXISTS user_feedback CASCADE;
DROP TABLE IF EXISTS user_activity CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS weekly_reports CASCADE;
DROP TABLE IF EXISTS daily_schedules CASCADE;
DROP TABLE IF EXISTS shift_changes CASCADE;
DROP TABLE IF EXISTS constant_schedules CASCADE;
DROP TABLE IF EXISTS rotating_patterns CASCADE;
DROP TABLE IF EXISTS users CASCADE;

DROP FUNCTION IF EXISTS log_user_activity() CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;

-- --- extensions ---
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- --- users ---
CREATE TABLE users (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    shift_type TEXT CHECK (shift_type IS NULL OR shift_type IN ('constant', 'rotating')),
    timezone TEXT DEFAULT 'Asia/Tashkent',
    notification_enabled BOOLEAN DEFAULT true,
    notification_prefs JSONB DEFAULT '{}'::jsonb,
    trial_started_at TIMESTAMPTZ DEFAULT NOW(),
    pro_expires_at TIMESTAMPTZ,
    last_pro_payment_at TIMESTAMPTZ,
    telegram_payment_charge_id TEXT,
    telegram_subscription_id TEXT,
    subscription_cancelled BOOLEAN NOT NULL DEFAULT false,
    subscription_active BOOLEAN NOT NULL DEFAULT true,
    last_payment_is_recurring BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_notification ON users(notification_enabled) WHERE notification_enabled = true;

CREATE INDEX idx_users_pro_expires ON users(pro_expires_at) WHERE pro_expires_at IS NOT NULL;

-- --- constant schedules ---
CREATE TABLE constant_schedules (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    work_start TIME NOT NULL,
    work_end TIME NOT NULL,
    sleep_start TIME,
    sleep_end TIME,
    shift_type TEXT CHECK (shift_type IN ('day', 'evening', 'night')),
    coffee_windows JSONB DEFAULT '[]'::jsonb,
    meal_windows JSONB DEFAULT '[]'::jsonb,
    brightness_windows JSONB DEFAULT '[]'::jsonb,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_constant_schedules_active ON constant_schedules(user_id, active) WHERE active = true;

-- --- rotating patterns ---
CREATE TABLE rotating_patterns (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    pattern_name TEXT,
    cycle_days INTEGER,
    pattern_start_date DATE,
    shifts JSONB DEFAULT '{}'::jsonb,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rotating_patterns_user ON rotating_patterns(user_id) WHERE active = true;

-- --- daily schedules ---
CREATE TABLE daily_schedules (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    shift_type TEXT CHECK (shift_type IN ('day', 'evening', 'night', 'off')),
    work_start TIME,
    work_end TIME,
    sleep_start TIME,
    sleep_end TIME,
    is_custom BOOLEAN DEFAULT false,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE INDEX idx_daily_schedules_user_date ON daily_schedules(user_id, date);
CREATE INDEX idx_daily_schedules_date ON daily_schedules(date);

-- --- shift changes ---
CREATE TABLE shift_changes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    original_date DATE NOT NULL,
    new_start TIME,
    new_end TIME,
    transition_day BOOLEAN DEFAULT false,
    transition_advice TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- --- notifications ---
CREATE TABLE notifications (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type TEXT CHECK (type IN ('coffee', 'meal', 'sleep', 'brightness', 'caffeine_check', 'transition', 'custom')),
    scheduled_time TIMESTAMPTZ NOT NULL,
    sent BOOLEAN DEFAULT false,
    sent_at TIMESTAMPTZ,
    acknowledged BOOLEAN DEFAULT false,
    acknowledged_at TIMESTAMPTZ,
    message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_sent ON notifications(user_id, sent) WHERE sent = false;
CREATE INDEX idx_notifications_scheduled ON notifications(scheduled_time) WHERE sent = false;
CREATE INDEX idx_notifications_type ON notifications(type);
CREATE INDEX idx_notifications_user_time_pending ON notifications(user_id, scheduled_time) WHERE sent = false;

-- --- weekly reports ---
CREATE TABLE weekly_reports (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    adherence_score DECIMAL(5,2),
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, week_start)
);

CREATE INDEX idx_weekly_reports_user ON weekly_reports(user_id);

-- --- end-of-shift summaries (mini-app sliders) ---
CREATE TABLE shift_summaries (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_date DATE NOT NULL,
    energy SMALLINT CHECK (energy IS NULL OR (energy >= 1 AND energy <= 4)),
    sleep_quality SMALLINT CHECK (sleep_quality IS NULL OR (sleep_quality >= 1 AND sleep_quality <= 4)),
    responses JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, local_date)
);

CREATE INDEX idx_shift_summaries_user_date ON shift_summaries(user_id, local_date DESC);

CREATE TABLE shift_details (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_date DATE NOT NULL,
    bed_time TIME,
    wake_time TIME,
    sleep_latency TEXT,
    night_wakings INTEGER,
    room_darkness TEXT,
    temperature TEXT,
    caffeine_cups INTEGER,
    last_caffeine_time TIME,
    caffeine_after_6pm BOOLEAN,
    screens_before_bed BOOLEAN,
    screens_minutes INTEGER,
    bright_light_morning BOOLEAN,
    dim_lights_before_sleep BOOLEAN,
    last_meal_time TIME,
    ate_near_bedtime BOOLEAN,
    hungry_during_sleep BOOLEAN,
    tired_at TIME,
    took_breaks BOOLEAN,
    stress BOOLEAN,
    stress_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, local_date)
);

CREATE INDEX idx_shift_details_user_date ON shift_details(user_id, local_date DESC);

-- --- feedback ---
CREATE TABLE user_feedback (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    feedback_type TEXT CHECK (feedback_type IN ('bug', 'feature', 'general', 'compliment')),
    message TEXT NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- --- activity log ---
CREATE TABLE user_activity (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    activity_type TEXT CHECK (activity_type IN ('command', 'notification_received', 'notification_ack', 'schedule_view', 'schedule_update', 'day_off')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_user_activity_user_date ON user_activity(user_id, created_at);
CREATE INDEX idx_user_activity_type ON user_activity(activity_type);

-- --- functions & triggers ---
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_constant_schedules_updated_at
    BEFORE UPDATE ON constant_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE FUNCTION log_user_activity()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_activity (user_id, activity_type, metadata)
    VALUES (
        NEW.user_id,
        'schedule_update',
        jsonb_build_object('table', TG_TABLE_NAME, 'schedule_id', NEW.id)
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER log_schedule_update
    AFTER INSERT ON constant_schedules
    FOR EACH ROW
    EXECUTE FUNCTION log_user_activity();

-- --- views ---
CREATE OR REPLACE VIEW active_users_with_schedules AS
SELECT
    u.id,
    u.telegram_id,
    u.first_name,
    u.timezone,
    u.notification_enabled,
    cs.work_start,
    cs.work_end,
    cs.sleep_start,
    cs.sleep_end,
    cs.coffee_windows,
    cs.meal_windows,
    cs.brightness_windows,
    cs.shift_type
FROM users u
JOIN constant_schedules cs ON u.id = cs.user_id
WHERE cs.active = true AND u.notification_enabled = true;

CREATE OR REPLACE VIEW todays_notifications AS
SELECT
    n.*,
    u.telegram_id,
    u.first_name
FROM notifications n
JOIN users u ON n.user_id = u.id
WHERE DATE(n.scheduled_time) = CURRENT_DATE
ORDER BY n.scheduled_time;

-- =============================================================================
-- Done. You should see "Success. No rows returned" (or similar).
-- =============================================================================
