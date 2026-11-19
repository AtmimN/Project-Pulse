-- Skema Database SQLite ProjectPulse
-- Mode WAL dan Foreign Keys diaktifkan pada level koneksi.

CREATE TABLE IF NOT EXISTS repos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT    UNIQUE NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('monitor', 'training')),
    active      INTEGER NOT NULL DEFAULT 1,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_rows (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id           INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    release_tag       TEXT,
    release_date      TEXT,
    first_commit_date TEXT,
    duration_months   REAL,
    n_contributors    INTEGER,
    n_work_items      INTEGER,
    kloc              REAL,
    included          INTEGER NOT NULL DEFAULT 1,
    exclusion_reason  TEXT,
    built_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS repo_snapshots (
    repo_id           INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    as_of             TEXT    NOT NULL,
    snapshot_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    n_contributors    INTEGER,
    n_work_items      INTEGER,
    kloc              REAL,
    first_commit_date TEXT,
    release_tag       TEXT,
    release_date      TEXT,
    duration_months   REAL,
    PRIMARY KEY (repo_id, as_of)
);

CREATE TABLE IF NOT EXISTS issues (
    repo_id    INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    number     INTEGER NOT NULL,
    is_pr      INTEGER NOT NULL DEFAULT 0,
    labels     TEXT    NOT NULL DEFAULT '[]',
    state      TEXT    NOT NULL DEFAULT 'open',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (repo_id, number)
);

CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id         INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL CHECK (kind IN ('issue_comment', 'review_comment')),
    comment_id      INTEGER NOT NULL,
    issue_number    INTEGER NOT NULL,
    is_pr           INTEGER NOT NULL DEFAULT 0,
    labels          TEXT    NOT NULL DEFAULT '[]',
    body            TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    sentiment_score REAL,
    sentiment_label TEXT    CHECK (sentiment_label IN ('positif', 'netral', 'negatif')),
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (kind, comment_id)
);
CREATE INDEX IF NOT EXISTS idx_comments_repo_created ON comments(repo_id, created_at);

CREATE TABLE IF NOT EXISTS releases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id      INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    release_id   INTEGER UNIQUE NOT NULL,
    tag          TEXT    NOT NULL,
    name         TEXT,
    published_at TEXT    NOT NULL,
    prerelease   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_releases_repo_pub ON releases(repo_id, published_at);

CREATE TABLE IF NOT EXISTS scrape_state (
    repo_id          INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    stream           TEXT    NOT NULL,
    last_updated_at  TEXT,
    floor_created_at TEXT,
    last_success_at  TEXT,
    PRIMARY KEY (repo_id, stream)
);

CREATE TABLE IF NOT EXISTS daily_stats (
    repo_id    INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    stat_date  TEXT    NOT NULL,
    n_comments INTEGER NOT NULL DEFAULT 0,
    n_positive INTEGER NOT NULL DEFAULT 0,
    n_neutral  INTEGER NOT NULL DEFAULT 0,
    n_negative INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (repo_id, stat_date)
);

CREATE TABLE IF NOT EXISTS keywords (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT    UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS keyword_daily (
    repo_id   INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    stat_date TEXT    NOT NULL,
    keyword   TEXT    NOT NULL,
    n_hits    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (repo_id, stat_date, keyword)
);

CREATE TABLE IF NOT EXISTS conversation_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    message    TEXT    NOT NULL,
    intent     TEXT,
    reply      TEXT    NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_logs_session ON conversation_logs(session_id);

CREATE TABLE IF NOT EXISTS estimations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    input_payload  TEXT    NOT NULL,
    result_payload TEXT    NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id     INTEGER PRIMARY KEY,
    sensitivity TEXT    NOT NULL DEFAULT 'sedang' CHECK (sensitivity IN ('rendah', 'sedang', 'tinggi')),
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    chat_id INTEGER NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    PRIMARY KEY (chat_id, repo_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id    INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    alert_type TEXT    NOT NULL,
    strength   TEXT    NOT NULL CHECK (strength IN ('lemah', 'sedang', 'kuat')),
    detail     TEXT    NOT NULL DEFAULT '{}',
    alert_date TEXT    NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dedupe_key TEXT    UNIQUE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_repo_date ON alerts(repo_id, alert_date);

CREATE TABLE IF NOT EXISTS alert_deliveries (
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    chat_id  INTEGER NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    status   TEXT    NOT NULL DEFAULT 'menunggu' CHECK (status IN ('menunggu', 'terkirim', 'gagal')),
    attempts INTEGER NOT NULL DEFAULT 0,
    sent_at  TIMESTAMP,
    PRIMARY KEY (alert_id, chat_id)
);

CREATE TABLE IF NOT EXISTS alert_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digest_log (
    chat_id     INTEGER NOT NULL REFERENCES subscribers(chat_id) ON DELETE CASCADE,
    digest_date TEXT    NOT NULL,
    PRIMARY KEY (chat_id, digest_date)
);

CREATE TABLE IF NOT EXISTS job_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name     TEXT    NOT NULL,
    trigger      TEXT    NOT NULL,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT,
    status       TEXT    NOT NULL CHECK (status IN ('berjalan', 'berhasil', 'sebagian', 'gagal')),
    new_comments INTEGER NOT NULL DEFAULT 0,
    new_releases INTEGER NOT NULL DEFAULT 0,
    detail       TEXT
);

-- Kata kunci awal bawaan (crash, login, error, broken, regression)
INSERT OR IGNORE INTO keywords (word) VALUES
    ('crash'),
    ('login'),
    ('error'),
    ('broken'),
    ('regression');
