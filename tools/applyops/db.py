"""
Shared SQLite data layer for ApplyOps.

All schema, connection management, and query functions live here.
Both the CLI and web UI import from this module.
"""
from __future__ import annotations

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
"""


def get_conn() -> sqlite3.Connection:
    """Get a connection to the SQLite database, creating schema if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


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
    cur = conn.execute(
        "INSERT INTO companies (name, url, description) VALUES (?, ?, ?)",
        (name, url, description),
    )
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
    company_id = None
    company_name = company
    if company:
        co = company_find(company)
        if co:
            company_id = co["id"]
            company_name = co["name"]
        else:
            # Auto-create company
            cur = conn.execute("INSERT INTO companies (name) VALUES (?)", (company,))
            row_id = cur.lastrowid
            co_row = conn.execute("SELECT * FROM companies WHERE rowid = ?", (row_id,)).fetchone()
            company_id = co_row["id"]
            company_name = company
            _log_action(conn, "cli", "auto-created company", "company", company_id)

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
    _log_action(conn, agent, action, entity_type, entity_id, details)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM task_runs ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return dict(row)


def log_list(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
