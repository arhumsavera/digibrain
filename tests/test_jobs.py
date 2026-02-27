"""Regression tests for existing ApplyOps (jobs pipeline) — must not break."""
import tools.applyops.db as db


class TestCompanies:
    def test_add(self):
        co = db.company_add("TestCorp", url="https://test.com", description="Test company")
        assert co["name"] == "TestCorp"

    def test_add_idempotent(self):
        """Adding the same company twice returns the existing one."""
        first = db.company_add("IdempotentCo")
        second = db.company_add("IdempotentCo")
        assert first["id"] == second["id"]

    def test_find_by_name(self):
        found = db.company_find("TestCorp")
        assert found is not None
        assert found["name"] == "TestCorp"

    def test_find_fuzzy(self):
        found = db.company_find("test")
        assert found is not None
        assert found["name"] == "TestCorp"


class TestJobs:
    def test_add_with_company(self):
        job = db.job_add(title="Engineer", company="TestCorp", source="manual")
        assert job["title"] == "Engineer"
        assert job["company_name"] == "TestCorp"
        assert job["status"] == "discovered"

    def test_update(self):
        job = db.job_add(title="Updatable", company="TestCorp")
        updated = db.job_update(job["id"], status="approved", notes="Looks good")
        assert updated["status"] == "approved"
        assert updated["notes"] == "Looks good"

    def test_list_filtered(self):
        jobs = db.job_list(status="approved")
        assert len(jobs) >= 1
        assert all(j["status"] == "approved" for j in jobs)

    def test_auto_create_company(self):
        job = db.job_add(title="Designer", company="AutoCreatedCo")
        assert job["company_name"] == "AutoCreatedCo"
        assert db.company_find("AutoCreatedCo") is not None

    def test_remove(self):
        job = db.job_add(title="ToRemove")
        assert db.job_remove(job["id"]) is True
        assert db.job_get(job["id"]) is None


class TestResumes:
    def test_add_and_find(self):
        resume = db.resume_add(name="test-base", content='{"name":"Test"}')
        assert resume["name"] == "test-base"

        found = db.resume_find("test-base")
        assert found is not None
        assert found["id"] == resume["id"]


class TestApplications:
    def test_lifecycle(self):
        job = db.job_add(title="AppTestJob", company="TestCorp")
        resume = db.resume_find("test-base")
        app = db.app_add(job_id=job["id"], resume_id=resume["id"])
        assert app["job_id"] == job["id"]

        updated = db.app_update(app["id"], status="applied")
        assert updated["applied_at"] is not None
        assert updated["status"] == "applied"

    def test_remove(self):
        job = db.job_add(title="AppRemoveJob")
        app = db.app_add(job_id=job["id"])
        assert db.app_remove(app["id"]) is True
        assert db.app_get(app["id"]) is None


class TestEmails:
    def test_add_and_list(self):
        job = db.job_add(title="EmailTestJob")
        email = db.email_add(
            sender="recruiter@test.com", subject="Opportunity",
            body="Great role for you...", job_id=job["id"],
        )
        assert email["sender"] == "recruiter@test.com"

        emails = db.email_list(limit=5)
        assert len(emails) >= 1


class TestMatches:
    def test_add(self):
        job = db.job_add(title="MatchTestJob")
        resume = db.resume_find("test-base")
        match = db.match_add(
            job_id=job["id"], resume_id=resume["id"], score=85,
            strong_matches='["python"]', gaps='["go"]',
        )
        assert match["score"] == 85


class TestStatsAndLogs:
    def test_global_stats(self):
        stats = db.get_stats()
        assert stats["companies"] >= 1
        assert isinstance(stats["jobs_by_status"], dict)

    def test_log_add(self):
        log = db.log_add(agent="test", action="tested", entity_type="test", entity_id="123")
        assert log["agent"] == "test"
        assert log["action"] == "tested"

    def test_log_list(self):
        logs = db.log_list(limit=5)
        assert len(logs) >= 1
