-- Nightflow canonical schema (v2)
-- CLI: apply via supabase/migrations/20260330120000_nightflow_initial.sql (keep in sync with this file).
-- Existing DB with old schema only: use upgrade_v1_to_v2.sql instead.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==================== USERS ====================
CREATE TABLE users (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    shift_type TEXT CHECK (shift_type IN ('constant', 'rotating') OR shift_type IS NULL),
    timezone TEXT DEFAULT 'Asia/Tashkent',
    notification_enabled BOOLEAN DEFAULT true,
    -- Per-category toggles (mini-app Settings); all optional, merge with app defaults
    notification_prefs JSONB DEFAULT '{}'::jsonb,
    trial_started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    pro_expires_at TIMESTAMP WITH TIME ZONE,
    last_pro_payment_at TIMESTAMP WITH TIME ZONE,
    telegram_payment_charge_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_notification ON users(notification_enabled) WHERE notification_enabled = true;

CREATE INDEX idx_users_pro_expires ON users(pro_expires_at) WHERE pro_expires_at IS NOT NULL;

-- ==================== CONSTANT SCHEDULES ====================
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_constant_schedules_active ON constant_schedules(user_id, active) WHERE active = true;

-- ==================== ROTATING PATTERNS ====================
CREATE TABLE rotating_patterns (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    pattern_name TEXT,
    cycle_days INTEGER,
    pattern_start_date DATE,
    shifts JSONB DEFAULT '{}'::jsonb,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_rotating_patterns_user ON rotating_patterns(user_id) WHERE active = true;

-- ==================== DAILY SCHEDULES ====================
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE INDEX idx_daily_schedules_user_date ON daily_schedules(user_id, date);
CREATE INDEX idx_daily_schedules_date ON daily_schedules(date);

-- ==================== SHIFT CHANGES ====================
CREATE TABLE shift_changes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    original_date DATE NOT NULL,
    new_start TIME,
    new_end TIME,
    transition_day BOOLEAN DEFAULT false,
    transition_advice TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ==================== NOTIFICATIONS ====================
CREATE TABLE notifications (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type TEXT CHECK (type IN ('coffee', 'meal', 'sleep', 'brightness', 'caffeine_check', 'transition', 'custom')),
    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
    sent BOOLEAN DEFAULT false,
    sent_at TIMESTAMP WITH TIME ZONE,
    acknowledged BOOLEAN DEFAULT false,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_sent ON notifications(user_id, sent) WHERE sent = false;
CREATE INDEX idx_notifications_scheduled ON notifications(scheduled_time) WHERE sent = false;
CREATE INDEX idx_notifications_type ON notifications(type);
CREATE INDEX idx_notifications_user_time_pending ON notifications(user_id, scheduled_time) WHERE sent = false;

-- ==================== WEEKLY REPORTS ====================
CREATE TABLE weekly_reports (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    adherence_score DECIMAL(5,2),
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, week_start)
);

CREATE INDEX idx_weekly_reports_user ON weekly_reports(user_id);

-- ==================== END OF SHIFT SUMMARIES (mini-app sliders) ====================
CREATE TABLE shift_summaries (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_date DATE NOT NULL,
    energy SMALLINT CHECK (energy IS NULL OR (energy >= 1 AND energy <= 4)),
    sleep_quality SMALLINT CHECK (sleep_quality IS NULL OR (sleep_quality >= 1 AND sleep_quality <= 4)),
    responses JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, local_date)
);

CREATE INDEX idx_shift_summaries_user_date ON shift_summaries(user_id, local_date DESC);

-- ==================== DETAILED SHIFT LOG (optional) ====================
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, local_date)
);

CREATE INDEX idx_shift_details_user_date ON shift_details(user_id, local_date DESC);

-- ==================== USER FEEDBACK ====================
CREATE TABLE user_feedback (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    feedback_type TEXT CHECK (feedback_type IN ('bug', 'feature', 'general', 'compliment')),
    message TEXT NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ==================== USER ACTIVITY ====================
CREATE TABLE user_activity (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    activity_type TEXT CHECK (activity_type IN ('command', 'notification_received', 'notification_ack', 'schedule_view', 'schedule_update', 'day_off')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_activity_user_date ON user_activity(user_id, created_at);
CREATE INDEX idx_user_activity_type ON user_activity(activity_type);

-- ==================== FUNCTIONS & TRIGGERS ====================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_constant_schedules_updated_at ON constant_schedules;
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

DROP TRIGGER IF EXISTS log_schedule_update ON constant_schedules;
CREATE TRIGGER log_schedule_update
    AFTER INSERT ON constant_schedules
    FOR EACH ROW
    EXECUTE FUNCTION log_user_activity();

-- ==================== VIEWS ====================
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
