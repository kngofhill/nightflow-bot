-- Optional detailed end-of-shift log (mini-app "Tell me more")
CREATE TABLE IF NOT EXISTS shift_details (
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

CREATE INDEX IF NOT EXISTS idx_shift_details_user_date ON shift_details(user_id, local_date DESC);
