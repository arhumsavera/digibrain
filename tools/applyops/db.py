"""
Shared SQLite data layer for ApplyOps and the generic domain store.

All schema, connection management, and query functions live here.
Both the CLI and web UI import from this module.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent.parent / "data" / "applyops.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    url TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    title TEXT NOT NULL,
    company_id TEXT REFERENCES companies(id),
    company_name TEXT,
    description TEXT,
    url TEXT,
    source TEXT,
    status TEXT DEFAULT 'discovered',
    skills TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resumes (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    tailored_for_job_id TEXT REFERENCES jobs(id),
    pdf_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    job_id TEXT NOT NULL REFERENCES jobs(id),
    resume_id TEXT REFERENCES resumes(id),
    status TEXT DEFAULT 'draft',
    applied_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    sender TEXT,
    subject TEXT,
    body_preview TEXT,
    job_id TEXT REFERENCES jobs(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    job_id TEXT NOT NULL REFERENCES jobs(id),
    resume_id TEXT NOT NULL REFERENCES resumes(id),
    score INTEGER,
    strong_matches TEXT,
    gaps TEXT,
    red_flags TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    agent TEXT,
    action TEXT,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Generic domain store
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    schema TEXT,
    instructions TEXT,
    keywords TEXT,
    icon TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    domain_id TEXT NOT NULL REFERENCES domains(id),
    type TEXT NOT NULL DEFAULT 'note',
    title TEXT NOT NULL,
    data TEXT,
    tags TEXT,
    status TEXT DEFAULT 'active',
    priority INTEGER,
    due_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_items_domain ON items(domain_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(domain_id, status);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(domain_id, type);
CREATE INDEX IF NOT EXISTS idx_items_due ON items(due_at) WHERE due_at IS NOT NULL;
"""

# FTS5 created separately (executescript doesn't handle virtual table IF NOT EXISTS well
# across all SQLite versions)
_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, data, tags,
    content=items, content_rowid=rowid
);
"""

# Triggers keep FTS5 in sync with the items table automatically.
# This replaces manual FTS inserts/deletes in item_add/update/remove.
_FTS_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS items_fts_insert AFTER INSERT ON items BEGIN
        INSERT INTO items_fts(rowid, title, data, tags)
        VALUES (new.rowid, new.title, COALESCE(new.data, ''), COALESCE(new.tags, ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS items_fts_delete AFTER DELETE ON items BEGIN
        INSERT INTO items_fts(items_fts, rowid, title, data, tags)
        VALUES ('delete', old.rowid, COALESCE(old.title, ''), COALESCE(old.data, ''), COALESCE(old.tags, ''));
    END""",
    """CREATE TRIGGER IF NOT EXISTS items_fts_update AFTER UPDATE ON items BEGIN
        INSERT INTO items_fts(items_fts, rowid, title, data, tags)
        VALUES ('delete', old.rowid, COALESCE(old.title, ''), COALESCE(old.data, ''), COALESCE(old.tags, ''));
        INSERT INTO items_fts(rowid, title, data, tags)
        VALUES (new.rowid, new.title, COALESCE(new.data, ''), COALESCE(new.tags, ''));
    END""",
]

# Instructions bootstrapped into the "jobs" domain so agents can load them dynamically
_JOBS_INSTRUCTIONS = """\
## ApplyOps (Job Application Tracker)

Local CLI tool backed by SQLite. Use `uv run applyops` for all operations.

### Companies
```
uv run applyops company add "Meta" --url "..." --description "..."
uv run applyops company list [--json]
uv run applyops company show <id-or-name> [--json]
```

### Jobs
```
uv run applyops job add --title "SWE" --company "Meta" [--url "..." --source email --description "..."]
uv run applyops job list [--status discovered|approved|rejected] [--company "Meta"] [--json]
uv run applyops job show <id> [--json]
uv run applyops job update <id> --status approved [--notes "..." --skills '["python","ml"]']
uv run applyops job remove <id>
```

### Resumes
```
uv run applyops resume add --name "base" --file resume.md
uv run applyops resume add --name "base" --content "markdown text..."
uv run applyops resume list [--json]
uv run applyops resume show <id-or-name> [--json] [--full]
uv run applyops resume render <id-or-name> [-o path.pdf]
```

**Resume rules:**
- When the user asks for a resume, ALWAYS render a PDF via `resume render`.
- The bot auto-detects PDF paths in your output and sends them as Telegram documents.
- Default output goes to `data/output/{name}_{id[:8]}.pdf`.
- Resume content is stored as JSON in the DB matching the Typst template schema.
- For tailored resumes: create a new resume entry with a descriptive name, render it, then the user gets a unique PDF.

### Applications
```
uv run applyops app add --job <job_id> [--resume <resume_id>]
uv run applyops app list [--status draft|applied|interviewing|offered|rejected] [--json]
uv run applyops app show <id> [--json]
uv run applyops app update <id> --status applied [--notes "..."]
uv run applyops app remove <id>
```

### Emails
```
uv run applyops email add --sender "..." --subject "..." [--body "..." --job <job_id>]
uv run applyops email list [--limit 10] [--json]
```

### Stats & Logs
```
uv run applyops stats [--json]
uv run applyops log add --agent claude --action "analyzed job" --entity-type job --entity-id <id>
uv run applyops log list [--limit 20] [--json]
```

### Workflow examples
- **"Check this job link"**: Fetch the URL, extract info, then `job add` with details
- **"Parse this recruiter email"**: Read the email, then `email add` + `job add` with extracted info
- **"How's my pipeline?"**: `stats` or `app list`
- **"Approve a job"**: `job update <id> --status approved`
- **"Show me my resume"**: `resume render base`
- **"Tailor my resume for this job"**: Read job desc + base resume, create tailored JSON, `resume add --name "company-role"`, `resume render company-role`.
"""


_conn_cache: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    """Get the cached connection to the SQLite database, creating schema on first call."""
    global _conn_cache
    if _conn_cache is not None:
        return _conn_cache
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    # FTS5 virtual table + auto-sync triggers
    try:
        conn.executescript(_FTS_SCHEMA)
        for trigger in _FTS_TRIGGERS:
            conn.execute(trigger)
        conn.commit()
    except sqlite3.OperationalError:
        pass  # FTS5 not available on this SQLite build
    _bootstrap(conn)
    _conn_cache = conn
    return conn


def _bootstrap(conn: sqlite3.Connection):
    """Seed built-in domains if not present."""
    row = conn.execute("SELECT id FROM domains WHERE name = 'jobs'").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO domains (name, description, instructions, keywords, icon) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "jobs",
                "Job application tracking — companies, jobs, resumes, applications, emails",
                _JOBS_INSTRUCTIONS,
                json.dumps(["job", "jobs", "application", "resume", "company",
                            "recruiter", "hiring", "interview", "offer", "salary",
                            "compensation"]),
                "briefcase",
            ),
        )
        conn.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_action(conn: sqlite3.Connection, agent: str, action: str,
                entity_type: str, entity_id: str, details: str | None = None):
    conn.execute(
        "INSERT INTO task_runs (agent, action, entity_type, entity_id, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent, action, entity_type, entity_id, details),
    )


# --- Companies ---

def company_add(name: str, url: str | None = None,
                description: str | None = None) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO companies (name, url, description) VALUES (?, ?, ?)",
            (name, url, description),
        )
    except sqlite3.IntegrityError:
        # Already exists — return existing record
        existing = company_find(name)
        if existing:
            return existing
        raise
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM companies WHERE rowid = ?", (row_id,)).fetchone()
    _log_action(conn, "cli", "added company", "company", row["id"])
    conn.commit()
    return dict(row)


def company_list() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM companies ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def company_find(name_or_id: str) -> dict | None:
    """Find a company by exact ID or case-insensitive name match."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (name_or_id,)).fetchone()
    if row:
        return dict(row)
    row = conn.execute(
        "SELECT * FROM companies WHERE lower(name) = lower(?)", (name_or_id,)
    ).fetchone()
    if row:
        return dict(row)
    # Fuzzy: LIKE
    row = conn.execute(
        "SELECT * FROM companies WHERE lower(name) LIKE ?",
        (f"%{name_or_id.lower()}%",),
    ).fetchone()
    return dict(row) if row else None


# --- Jobs ---

def job_add(title: str, company: str | None = None, url: str | None = None,
            source: str | None = None, description: str | None = None) -> dict:
    conn = get_conn()
    try:
        company_id = None
        company_name = company
        if company:
            co = company_find(company)
            if co:
                company_id = co["id"]
                company_name = co["name"]
            else:
                # Auto-create company (idempotent)
                co = company_add(company)
                company_id = co["id"]
                company_name = co["name"]

        cur = conn.execute(
            "INSERT INTO jobs (title, company_id, company_name, url, source, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, company_id, company_name, url, source, description),
        )
        row_id = cur.lastrowid
        row = conn.execute("SELECT * FROM jobs WHERE rowid = ?", (row_id,)).fetchone()
        _log_action(conn, "cli", "added job", "job", row["id"])
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise


def job_list(status: str | None = None, company: str | None = None) -> list[dict]:
    conn = get_conn()
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if company:
        query += " AND lower(company_name) LIKE ?"
        params.append(f"%{company.lower()}%")
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def job_get(job_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def job_update(job_id: str, **kwargs) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    allowed = {"title", "status", "notes", "skills", "url", "source", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return dict(row)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [job_id]
    conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", vals)
    _log_action(conn, "cli", f"updated job ({', '.join(updates.keys())})", "job", job_id)
    conn.commit()
    return job_get(job_id)


def job_remove(job_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    _log_action(conn, "cli", "removed job", "job", job_id)
    conn.commit()
    return True


# --- Resumes ---

def resume_add(name: str, content: str,
               tailored_for_job_id: str | None = None) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO resumes (name, content, tailored_for_job_id) VALUES (?, ?, ?)",
        (name, content, tailored_for_job_id),
    )
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM resumes WHERE rowid = ?", (row_id,)).fetchone()
    _log_action(conn, "cli", "added resume", "resume", row["id"])
    conn.commit()
    return dict(row)


def resume_list() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM resumes ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def resume_set_pdf(resume_id: str, pdf_path: str) -> None:
    """Store the rendered PDF path for a resume."""
    conn = get_conn()
    conn.execute("UPDATE resumes SET pdf_path = ? WHERE id = ?", (pdf_path, resume_id))
    conn.commit()


def resume_find(name_or_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM resumes WHERE id = ?", (name_or_id,)).fetchone()
    if row:
        return dict(row)
    row = conn.execute(
        "SELECT * FROM resumes WHERE lower(name) = lower(?)", (name_or_id,)
    ).fetchone()
    if row:
        return dict(row)
    row = conn.execute(
        "SELECT * FROM resumes WHERE lower(name) LIKE ?",
        (f"%{name_or_id.lower()}%",),
    ).fetchone()
    return dict(row) if row else None


# --- Applications ---

def app_add(job_id: str, resume_id: str | None = None) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO applications (job_id, resume_id) VALUES (?, ?)",
        (job_id, resume_id),
    )
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM applications WHERE rowid = ?", (row_id,)).fetchone()
    _log_action(conn, "cli", "added application", "application", row["id"])
    conn.commit()
    return dict(row)


def app_list(status: str | None = None) -> list[dict]:
    conn = get_conn()
    query = """
        SELECT a.*, j.title as job_title, j.company_name
        FROM applications a
        LEFT JOIN jobs j ON a.job_id = j.id
        WHERE 1=1
    """
    params: list[Any] = []
    if status:
        query += " AND a.status = ?"
        params.append(status)
    query += " ORDER BY a.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def app_get(app_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT a.*, j.title as job_title, j.company_name "
        "FROM applications a LEFT JOIN jobs j ON a.job_id = j.id "
        "WHERE a.id = ?",
        (app_id,),
    ).fetchone()
    return dict(row) if row else None


def app_update(app_id: str, **kwargs) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not row:
        return None
    allowed = {"status", "notes", "applied_at", "resume_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return app_get(app_id)
    updates["updated_at"] = _now()
    if updates.get("status") == "applied" and not row["applied_at"]:
        updates["applied_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [app_id]
    conn.execute(f"UPDATE applications SET {set_clause} WHERE id = ?", vals)
    _log_action(conn, "cli", f"updated application ({', '.join(updates.keys())})", "application", app_id)
    conn.commit()
    return app_get(app_id)


def app_remove(app_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    _log_action(conn, "cli", "removed application", "application", app_id)
    conn.commit()
    return True


# --- Emails ---

def email_add(sender: str | None = None, subject: str | None = None,
              body: str | None = None, job_id: str | None = None) -> dict:
    conn = get_conn()
    body_preview = body[:500] if body else None
    cur = conn.execute(
        "INSERT INTO emails (sender, subject, body_preview, job_id) VALUES (?, ?, ?, ?)",
        (sender, subject, body_preview, job_id),
    )
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM emails WHERE rowid = ?", (row_id,)).fetchone()
    _log_action(conn, "cli", "added email", "email", row["id"])
    conn.commit()
    return dict(row)


def email_list(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM emails ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Matches ---

def match_add(job_id: str, resume_id: str, score: int | None = None,
              strong_matches: str | None = None, gaps: str | None = None,
              red_flags: str | None = None, notes: str | None = None) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO matches (job_id, resume_id, score, strong_matches, gaps, red_flags, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (job_id, resume_id, score, strong_matches, gaps, red_flags, notes),
    )
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM matches WHERE rowid = ?", (row_id,)).fetchone()
    _log_action(conn, "cli", "added match analysis", "match", row["id"])
    conn.commit()
    return dict(row)


def match_list(job_id: str | None = None, min_score: int | None = None) -> list[dict]:
    conn = get_conn()
    query = """
        SELECT m.*, j.title as job_title, j.company_name, r.name as resume_name
        FROM matches m
        LEFT JOIN jobs j ON m.job_id = j.id
        LEFT JOIN resumes r ON m.resume_id = r.id
        WHERE 1=1
    """
    params: list[Any] = []
    if job_id:
        query += " AND m.job_id = ?"
        params.append(job_id)
    if min_score is not None:
        query += " AND m.score >= ?"
        params.append(min_score)
    query += " ORDER BY m.score DESC, m.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def match_get(match_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT m.*, j.title as job_title, j.company_name, r.name as resume_name "
        "FROM matches m "
        "LEFT JOIN jobs j ON m.job_id = j.id "
        "LEFT JOIN resumes r ON m.resume_id = r.id "
        "WHERE m.id = ?",
        (match_id,),
    ).fetchone()
    return dict(row) if row else None


# --- Stats ---

def get_stats() -> dict:
    conn = get_conn()
    stats = {}
    for table in ("companies", "jobs", "resumes", "applications", "emails", "matches"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[table] = count

    # Job status breakdown
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
    ).fetchall()
    stats["jobs_by_status"] = {r["status"]: r["cnt"] for r in rows}

    # Application status breakdown
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM applications GROUP BY status"
    ).fetchall()
    stats["apps_by_status"] = {r["status"]: r["cnt"] for r in rows}

    return stats


# --- Task Runs ---

def log_add(agent: str, action: str, entity_type: str,
            entity_id: str, details: str | None = None) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO task_runs (agent, action, entity_type, entity_id, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent, action, entity_type, entity_id, details),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM task_runs WHERE rowid = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


def log_list(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Domains ---

def domain_add(name: str, description: str | None = None,
               keywords: str | None = None, instructions: str | None = None,
               schema: str | None = None, icon: str | None = None) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO domains (name, description, keywords, instructions, schema, icon) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, keywords, instructions, schema, icon),
        )
    except sqlite3.IntegrityError:
        # Already exists — return existing record
        existing = domain_find(name)
        if existing:
            return existing
        raise
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM domains WHERE rowid = ?", (row_id,)).fetchone()
    _log_action(conn, "cli", "added domain", "domain", row["id"])
    conn.commit()
    return dict(row)


def domain_list() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM domains ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def domain_find(name_or_id: str) -> dict | None:
    """Find a domain by exact ID or case-insensitive name match."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM domains WHERE id = ?", (name_or_id,)).fetchone()
    if row:
        return dict(row)
    row = conn.execute(
        "SELECT * FROM domains WHERE lower(name) = lower(?)", (name_or_id,)
    ).fetchone()
    if row:
        return dict(row)
    row = conn.execute(
        "SELECT * FROM domains WHERE lower(name) LIKE ?",
        (f"%{name_or_id.lower()}%",),
    ).fetchone()
    return dict(row) if row else None


def domain_update(name_or_id: str, **kwargs) -> dict | None:
    d = domain_find(name_or_id)
    if not d:
        return None
    conn = get_conn()
    allowed = {"name", "description", "keywords", "instructions", "schema", "icon"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return d
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [d["id"]]
    conn.execute(f"UPDATE domains SET {set_clause} WHERE id = ?", vals)
    _log_action(conn, "cli", f"updated domain ({', '.join(updates.keys())})", "domain", d["id"])
    conn.commit()
    return domain_find(d["id"])


def domain_remove(name_or_id: str) -> bool:
    d = domain_find(name_or_id)
    if not d:
        return False
    conn = get_conn()
    # Remove all items in this domain first
    conn.execute("DELETE FROM items WHERE domain_id = ?", (d["id"],))
    conn.execute("DELETE FROM domains WHERE id = ?", (d["id"],))
    _log_action(conn, "cli", "removed domain", "domain", d["id"])
    conn.commit()
    return True


def detect_domain(message: str) -> list[dict]:
    """Score each domain against a message by keyword overlap.

    Returns domains sorted by score descending, filtered to score > 0.
    """
    conn = get_conn()
    domains = conn.execute("SELECT * FROM domains").fetchall()

    words = set(message.lower().split())
    message_lower = message.lower()

    results = []
    for d in domains:
        d = dict(d)
        kw_raw = d.get("keywords") or "[]"
        try:
            keywords = json.loads(kw_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not keywords:
            continue

        score = 0.0
        matched = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in words:
                score += 1.0
                matched.append(kw)
            elif kw_lower in message_lower:
                score += 0.5
                matched.append(kw)
            elif any(
                w.startswith(kw_lower) or kw_lower.startswith(w) or
                # Stem matching: "exercise" ↔ "exercising" (shared prefix minus inflection)
                # Require stem (word minus 2 chars) to be at least 4 chars
                (len(kw_lower) >= 6 and w.startswith(kw_lower[:-2])) or
                (len(w) >= 6 and kw_lower.startswith(w[:-2]))
                for w in words
            ):
                score += 0.5
                matched.append(kw)

        if score > 0:
            d["_score"] = round(score / len(keywords), 2)
            d["_matched"] = matched
            results.append(d)

    return sorted(results, key=lambda x: x["_score"], reverse=True)


# --- Items ---

def _resolve_domain(domain: str) -> dict:
    """Resolve a domain name/id or raise ValueError."""
    d = domain_find(domain)
    if not d:
        raise ValueError(f"Domain not found: {domain}")
    return d


def item_add(domain: str, title: str, type: str = "note",
             data: str | None = None, tags: str | None = None,
             status: str = "active", priority: int | None = None,
             due_at: str | None = None) -> dict:
    d = _resolve_domain(domain)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO items (domain_id, type, title, data, tags, status, priority, due_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (d["id"], type, title, data, tags, status, priority, due_at),
    )
    row_id = cur.lastrowid
    row = conn.execute("SELECT * FROM items WHERE rowid = ?", (row_id,)).fetchone()
    # FTS index is updated automatically via trigger
    _log_action(conn, "cli", f"added item ({type})", "item", row["id"])
    conn.commit()
    return dict(row)


def item_list(domain: str | None = None, type: str | None = None,
              status: str | None = None, sort: str = "created",
              limit: int = 50) -> list[dict]:
    conn = get_conn()
    query = """
        SELECT i.*, d.name as domain_name
        FROM items i
        LEFT JOIN domains d ON i.domain_id = d.id
        WHERE 1=1
    """
    params: list[Any] = []
    if domain:
        d = domain_find(domain)
        if not d:
            return []
        query += " AND i.domain_id = ?"
        params.append(d["id"])
    if type:
        query += " AND i.type = ?"
        params.append(type)
    if status:
        query += " AND i.status = ?"
        params.append(status)

    sort_map = {
        "created": "i.created_at DESC",
        "updated": "i.updated_at DESC",
        "due": "i.due_at ASC NULLS LAST",
        "priority": "i.priority ASC NULLS LAST, i.created_at DESC",
    }
    query += f" ORDER BY {sort_map.get(sort, 'i.created_at DESC')}"
    query += " LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def item_get(item_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT i.*, d.name as domain_name "
        "FROM items i LEFT JOIN domains d ON i.domain_id = d.id "
        "WHERE i.id = ?",
        (item_id,),
    ).fetchone()
    return dict(row) if row else None


def item_update(item_id: str, **kwargs) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return None
    allowed = {"title", "type", "data", "tags", "status", "priority", "due_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return item_get(item_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [item_id]
    conn.execute(f"UPDATE items SET {set_clause} WHERE id = ?", vals)
    # FTS index is updated automatically via trigger
    _log_action(conn, "cli", f"updated item ({', '.join(updates.keys())})", "item", item_id)
    conn.commit()
    return item_get(item_id)


def item_remove(item_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return False
    # FTS index is cleaned up automatically via trigger
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    _log_action(conn, "cli", "removed item", "item", item_id)
    conn.commit()
    return True


def item_search(query: str, domain: str | None = None,
                limit: int = 20) -> list[dict]:
    """Full-text search across items using FTS5."""
    conn = get_conn()
    sql = """
        SELECT i.*, d.name as domain_name,
               rank as _rank
        FROM items_fts fts
        JOIN items i ON i.rowid = fts.rowid
        LEFT JOIN domains d ON i.domain_id = d.id
        WHERE items_fts MATCH ?
    """
    params: list[Any] = [query]
    if domain:
        d = domain_find(domain)
        if d:
            sql += " AND i.domain_id = ?"
            params.append(d["id"])
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []  # FTS not available


def item_stats(domain: str) -> dict:
    """Get item counts grouped by type and status for a domain."""
    d = _resolve_domain(domain)
    conn = get_conn()

    total = conn.execute(
        "SELECT COUNT(*) FROM items WHERE domain_id = ?", (d["id"],)
    ).fetchone()[0]

    by_type = conn.execute(
        "SELECT type, COUNT(*) as cnt FROM items WHERE domain_id = ? GROUP BY type",
        (d["id"],),
    ).fetchall()

    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM items WHERE domain_id = ? GROUP BY status",
        (d["id"],),
    ).fetchall()

    return {
        "domain": d["name"],
        "total": total,
        "by_type": {r["type"]: r["cnt"] for r in by_type},
        "by_status": {r["status"]: r["cnt"] for r in by_status},
    }
