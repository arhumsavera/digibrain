"""Tests for database bootstrap — jobs domain auto-seeding."""
import json

import tools.applyops.db as db


class TestBootstrap:
    def test_jobs_domain_exists(self, conn):
        row = conn.execute("SELECT * FROM domains WHERE name = 'jobs'").fetchone()
        assert row is not None

    def test_jobs_has_keywords(self, conn):
        row = conn.execute("SELECT keywords FROM domains WHERE name = 'jobs'").fetchone()
        kws = json.loads(row["keywords"])
        assert "resume" in kws
        assert "job" in kws

    def test_jobs_has_instructions(self, conn):
        row = conn.execute("SELECT instructions FROM domains WHERE name = 'jobs'").fetchone()
        assert len(row["instructions"]) > 100

    def test_jobs_has_icon(self, conn):
        row = conn.execute("SELECT icon FROM domains WHERE name = 'jobs'").fetchone()
        assert row["icon"] == "briefcase"

    def test_bootstrap_idempotent(self, conn):
        db._bootstrap(conn)
        db._bootstrap(conn)
        count = conn.execute("SELECT COUNT(*) FROM domains WHERE name = 'jobs'").fetchone()[0]
        assert count == 1

    def test_all_tables_exist(self, conn):
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        for expected in ["companies", "jobs", "resumes", "applications",
                         "emails", "matches", "task_runs", "domains", "items"]:
            assert expected in tables, f"Missing table: {expected}"
