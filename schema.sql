-- ═══════════════════════════════════════════════
--  CASEOPS BACKEND — DATABASE SCHEMA
-- ═══════════════════════════════════════════════

-- Main cases table. One row per Case Number.
-- We keep the common fields as real columns (for filtering/sorting),
-- AND store the full original Excel row as JSON in raw_json,
-- so we never lose a column even if the sheet has extra fields.
CREATE TABLE IF NOT EXISTS cases (
    case_number       TEXT PRIMARY KEY,
    status            TEXT,
    account           TEXT,
    owner             TEXT,
    age               INTEGER,
    pending_with      TEXT,
    inc               TEXT,
    inc_age           INTEGER,
    inc_owner         TEXT,
    inc_owner_queue   TEXT,
    server             TEXT,       -- UAT / PROD
    delivery_date     TEXT,
    next_update       TEXT,
    jira_status       TEXT,
    latest_comment    TEXT,
    modified_by       TEXT,
    modified_date     TEXT,
    email_last_sent   TEXT,        -- client's last email to us
    last_email_sent   TEXT,        -- our last reply
    raw_json          TEXT,        -- full original row, as JSON
    updated_at        TEXT DEFAULT (datetime('now'))
);

-- Per-case internal notes (free text, one per case)
CREATE TABLE IF NOT EXISTS case_notes (
    case_number  TEXT PRIMARY KEY REFERENCES cases(case_number) ON DELETE CASCADE,
    notes        TEXT,
    updated_at   TEXT DEFAULT (datetime('now'))
);

-- Promise / commitment tracker (many per case)
CREATE TABLE IF NOT EXISTS promises (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number  TEXT REFERENCES cases(case_number) ON DELETE CASCADE,
    text         TEXT NOT NULL,
    date         TEXT NOT NULL,     -- YYYY-MM-DD
    owner        TEXT,              -- Client / Us / BCG / Developers
    done         INTEGER DEFAULT 0, -- 0/1
    created_at   TEXT DEFAULT (datetime('now'))
);

-- Client email log (many per case)
CREATE TABLE IF NOT EXISTS emails (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number    TEXT REFERENCES cases(case_number) ON DELETE CASCADE,
    subject        TEXT NOT NULL,
    direction      TEXT,            -- received / sent
    delivery_date  TEXT,
    timestamp      TEXT DEFAULT (datetime('now'))
);

-- Watchlist (starred cases), one row per case that's starred
CREATE TABLE IF NOT EXISTS watchlist (
    case_number  TEXT PRIMARY KEY REFERENCES cases(case_number) ON DELETE CASCADE,
    note         TEXT DEFAULT '',
    starred_at   TEXT DEFAULT (datetime('now'))
);
