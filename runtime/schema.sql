-- salesdataskills 本地 SQLite schema
-- 每个用户本地独立一份数据库，路径由 DATA_REPO_DB_PATH 决定。
-- 此文件由 runtime/init_db.py 读取执行。

-- ── schema 版本跟踪 ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS _schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    note        TEXT
);

-- ── CRM：销售线索 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_sales_leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    leads_id        TEXT UNIQUE,          -- CRM 业务 ID（去重键）
    raw_json        TEXT,                 -- 原始 JSON（完整保留，便于后续字段扩展）
    created_ts      INTEGER,              -- 创建时间戳（毫秒）
    synced_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ── CRM：企微聊天会话 ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_chat_session (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT UNIQUE,
    corp_id         TEXT,
    follow_user_id  TEXT,
    raw_json        TEXT,
    created_ts      INTEGER,
    synced_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ── CRM：外部好友跟进 ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_external_follow (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    follow_id       TEXT UNIQUE,
    raw_json        TEXT,
    created_ts      INTEGER,
    synced_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ── Metabase：抓取缓存 ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metabase_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id         INTEGER NOT NULL,
    param_key       TEXT NOT NULL DEFAULT '',  -- 参数 hash 或空字符串（无参数时）
    records_json    TEXT,                      -- 完整 JSON 数组
    row_count       INTEGER,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(card_id, param_key)
);

-- ── 同步日志 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name    TEXT NOT NULL,
    status      TEXT NOT NULL CHECK(status IN ('success', 'error', 'skipped')),
    rows_synced INTEGER DEFAULT 0,
    message     TEXT,
    started_at  TEXT,
    finished_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ── 初始化完成标记 ────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO _schema_version (version, note)
VALUES (1, 'initial schema');
