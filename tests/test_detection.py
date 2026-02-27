"""Tests for domain detection — keyword matching against user messages."""
import tools.applyops.db as db


class TestExactMatch:
    def test_jobs_resume_and_job(self, fitness_domain, todos_domain, reading_domain):
        results = db.detect_domain("I need to update my resume for the job application")
        assert len(results) > 0
        assert results[0]["name"] == "jobs"
        assert "resume" in results[0]["_matched"]

    def test_fitness_gym_workout(self, fitness_domain):
        results = db.detect_domain("went to the gym for a workout")
        assert len(results) > 0
        assert results[0]["name"] == "fitness"

    def test_todos_reminder_deadline(self, todos_domain):
        results = db.detect_domain("add a reminder for the deadline")
        assert len(results) > 0
        assert results[0]["name"] == "todos"

    def test_reading_book(self, reading_domain):
        results = db.detect_domain("I just finished reading a great book")
        assert len(results) > 0
        assert results[0]["name"] == "reading"


class TestNoMatch:
    def test_unrelated_message(self, fitness_domain, todos_domain, reading_domain):
        results = db.detect_domain("the weather is nice today")
        assert len(results) == 0

    def test_domain_without_keywords_never_matches(self):
        db.domain_add(name="no_kw_test", description="no keywords")
        results = db.detect_domain("anything at all")
        matched_names = [r["name"] for r in results]
        assert "no_kw_test" not in matched_names
        db.domain_remove("no_kw_test")


class TestMultiDomain:
    def test_overlapping_message(self, fitness_domain):
        results = db.detect_domain("I need to run to the gym for a job interview")
        assert len(results) >= 2
        matched_names = [r["name"] for r in results]
        assert "fitness" in matched_names
        assert "jobs" in matched_names

    def test_sorted_by_score(self, fitness_domain):
        results = db.detect_domain("I need to run to the gym for a job interview")
        scores = [r["_score"] for r in results]
        assert scores == sorted(scores, reverse=True)


class TestStemAndPrefix:
    def test_exercising_matches_exercise(self, fitness_domain):
        """exercise (8 chars) and exercising (10 chars) share stem 'exercis'."""
        results = db.detect_domain("exercising is great for health")
        assert len(results) > 0
        assert results[0]["name"] == "fitness"

    def test_running_matches_run(self, fitness_domain):
        """'run' is a substring of 'running in the park'."""
        results = db.detect_domain("running in the park")
        assert len(results) > 0
        assert results[0]["name"] == "fitness"

    def test_applications_matches_application(self):
        """'application' exact word match in jobs keywords."""
        results = db.detect_domain("I submitted my application today")
        assert len(results) > 0
        assert results[0]["name"] == "jobs"


class TestCaseInsensitive:
    def test_all_caps(self, fitness_domain):
        results = db.detect_domain("GOING TO THE GYM TODAY")
        assert len(results) > 0
        assert results[0]["name"] == "fitness"

    def test_mixed_case(self, fitness_domain):
        results = db.detect_domain("Going to the Gym")
        assert len(results) > 0
        assert results[0]["name"] == "fitness"
