CREATE TABLE IF NOT EXISTS daily_health (
    day TEXT PRIMARY KEY,
    sleep_score REAL,
    sleep_duration_hours REAL,
    deep_sleep_hours REAL,
    rem_sleep_hours REAL,
    sleep_efficiency REAL,
    bedtime_hour REAL,
    waketime_hour REAL,
    readiness_score REAL,
    activity_score REAL,
    resting_heart_rate REAL,
    hrv REAL,
    stress REAL,
    resilience REAL,
    spo2 REAL,
    vo2_max REAL,
    cardiovascular_age REAL,
    active_calories REAL,
    total_calories REAL,
    steps REAL,
    source_updated_at TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_health_day ON daily_health(day);
CREATE INDEX IF NOT EXISTS idx_daily_health_hrv ON daily_health(hrv);
CREATE INDEX IF NOT EXISTS idx_daily_health_sleep ON daily_health(sleep_score);

CREATE TABLE IF NOT EXISTS sync_state (
    resource TEXT PRIMARY KEY,
    cursor TEXT,
    last_sync TEXT,
    status TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS webhook_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    event_type TEXT,
    resource_id TEXT,
    payload TEXT NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id INTEGER PRIMARY KEY CHECK(id=1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER,
    scopes TEXT,
    updated_at TEXT NOT NULL
);
