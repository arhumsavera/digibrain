"""Tests for domain CRUD operations."""
import pytest

import tools.applyops.db as db


class TestDomainAdd:
    def test_returns_dict(self, fitness_domain):
        assert isinstance(fitness_domain, dict)

    def test_has_id(self, fitness_domain):
        assert len(fitness_domain["id"]) > 0

    def test_name_correct(self, fitness_domain):
        assert fitness_domain["name"] == "fitness"

    def test_has_timestamps(self, fitness_domain):
        assert fitness_domain["created_at"] is not None

    def test_duplicate_name_is_idempotent(self, fitness_domain):
        """Adding a domain that already exists returns the existing one."""
        duplicate = db.domain_add(name="fitness")
        assert duplicate["id"] == fitness_domain["id"]


class TestDomainFind:
    def test_by_name(self, fitness_domain):
        found = db.domain_find("fitness")
        assert found is not None
        assert found["name"] == "fitness"

    def test_by_id(self, fitness_domain):
        found = db.domain_find(fitness_domain["id"])
        assert found is not None
        assert found["id"] == fitness_domain["id"]

    def test_by_partial_name(self, fitness_domain):
        found = db.domain_find("fit")
        assert found is not None
        assert found["name"] == "fitness"

    def test_not_found(self):
        assert db.domain_find("zzz_nonexistent_zzz") is None


class TestDomainList:
    def test_returns_list(self, fitness_domain):
        domains = db.domain_list()
        assert isinstance(domains, list)

    def test_includes_bootstrap_and_added(self, fitness_domain):
        domains = db.domain_list()
        names = [d["name"] for d in domains]
        assert "jobs" in names
        assert "fitness" in names

    def test_sorted_by_name(self, fitness_domain):
        domains = db.domain_list()
        names = [d["name"] for d in domains]
        assert names == sorted(names)


class TestDomainUpdate:
    def test_update_description(self, fitness_domain):
        updated = db.domain_update("fitness", description="Fitness tracking and goals")
        assert updated is not None
        assert updated["description"] == "Fitness tracking and goals"

    def test_update_nonexistent(self):
        assert db.domain_update("zzz_nonexistent_zzz", description="x") is None


class TestDomainRemove:
    def test_remove_and_cascade(self):
        dom = db.domain_add(name="remove_test", description="to be removed")
        db.item_add(domain="remove_test", title="Item A")
        db.item_add(domain="remove_test", title="Item B")

        assert db.domain_remove("remove_test") is True
        assert db.domain_find("remove_test") is None

        # Items should be gone too
        conn = db.get_conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE domain_id = ?", (dom["id"],)
        ).fetchone()[0]
        assert count == 0

    def test_remove_nonexistent(self):
        assert db.domain_remove("zzz_nonexistent_zzz") is False
