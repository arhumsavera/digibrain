"""Tests for item CRUD, search, and stats."""
import json

import pytest

import tools.applyops.db as db


class TestItemAdd:
    def test_full_item(self, fitness_domain):
        item = db.item_add(
            domain="fitness", title="Morning run", type="workout",
            data=json.dumps({"distance": "5k", "time": "25min"}),
            tags=json.dumps(["running", "cardio"]),
        )
        assert isinstance(item, dict)
        assert len(item["id"]) > 0
        assert item["title"] == "Morning run"
        assert item["type"] == "workout"
        assert item["status"] == "active"
        assert item["domain_id"] == fitness_domain["id"]

    def test_with_priority(self, fitness_domain):
        item = db.item_add(
            domain="fitness", title="Bench press", type="workout",
            data=json.dumps({"weight": "135lbs", "sets": 3, "reps": 10}),
            tags=json.dumps(["strength", "chest"]),
            priority=1,
        )
        assert item["priority"] == 1

    def test_with_due_date(self, todos_domain):
        item = db.item_add(
            domain="todos", title="Buy groceries", type="task",
            due_at="2026-02-20", priority=2,
        )
        assert item["due_at"] == "2026-02-20"

    def test_minimal_item(self, todos_domain):
        item = db.item_add(domain="todos", title="Just a title")
        assert item["type"] == "note"
        assert item["data"] is None
        assert item["tags"] is None

    def test_bad_domain_raises(self):
        with pytest.raises(ValueError, match="Domain not found"):
            db.item_add(domain="nonexistent_domain", title="Should fail")


class TestItemGet:
    def test_get_existing(self, fitness_domain):
        item = db.item_add(domain="fitness", title="Get test", type="workout")
        fetched = db.item_get(item["id"])
        assert fetched is not None
        assert fetched["title"] == "Get test"
        assert fetched["domain_name"] == "fitness"

    def test_get_nonexistent(self):
        assert db.item_get("nonexistent") is None


class TestItemList:
    def test_by_domain(self, fitness_domain):
        items = db.item_list(domain="fitness")
        assert len(items) >= 1
        assert all(i["domain_name"] == "fitness" for i in items)

    def test_by_type(self, fitness_domain):
        items = db.item_list(domain="fitness", type="workout")
        assert all(i["type"] == "workout" for i in items)

    def test_all_domains(self, fitness_domain, todos_domain):
        items = db.item_list()
        domains = set(i["domain_name"] for i in items)
        assert len(domains) >= 2

    def test_by_status(self, fitness_domain):
        items = db.item_list(status="active")
        assert all(i["status"] == "active" for i in items)

    def test_sort_by_priority(self, fitness_domain):
        items = db.item_list(domain="fitness", sort="priority")
        priorities = [i["priority"] for i in items if i["priority"] is not None]
        assert priorities == sorted(priorities)


class TestItemUpdate:
    def test_update_fields(self, fitness_domain):
        item = db.item_add(domain="fitness", title="Update test")
        updated = db.item_update(item["id"], status="done", title="Updated title")
        assert updated is not None
        assert updated["title"] == "Updated title"
        assert updated["status"] == "done"

    def test_update_nonexistent(self):
        assert db.item_update("nonexistent", title="x") is None


class TestItemRemove:
    def test_remove_existing(self, fitness_domain):
        item = db.item_add(domain="fitness", title="To be removed", type="temp")
        assert db.item_remove(item["id"]) is True
        assert db.item_get(item["id"]) is None

    def test_remove_nonexistent(self):
        assert db.item_remove("nonexistent") is False


class TestFTS5Search:
    @pytest.fixture(autouse=True, scope="class")
    def _seed_searchable_items(self, reading_domain, fitness_domain):
        """Seed items for search tests (once per class)."""
        db.item_add(domain="reading", title="Deep Work by Cal Newport", type="book",
                     data=json.dumps({"author": "Cal Newport", "genre": "productivity"}))
        db.item_add(domain="reading", title="Atomic Habits by James Clear", type="book",
                     data=json.dumps({"author": "James Clear", "genre": "self-help"}))
        db.item_add(domain="fitness", title="Deep stretch routine", type="routine",
                     data=json.dumps({"duration": "20min"}))

    def test_search_by_title(self):
        results = db.item_search("Deep")
        assert len(results) >= 2
        titles = [r["title"] for r in results]
        assert any("Deep Work" in t for t in titles)
        assert any("Deep stretch" in t for t in titles)

    def test_search_scoped_to_domain(self):
        results = db.item_search("Deep", domain="reading")
        assert len(results) == 1
        assert results[0]["title"] == "Deep Work by Cal Newport"

    def test_search_in_data_field(self):
        results = db.item_search("Newport")
        assert len(results) >= 1

    def test_search_no_results(self):
        results = db.item_search("quantum physics")
        assert len(results) == 0

    def test_search_in_tags(self, fitness_domain):
        item = db.item_add(domain="fitness", title="Tag search test",
                            tags=json.dumps(["searchable_unique_tag"]))
        results = db.item_search("searchable_unique_tag")
        assert len(results) >= 1
        db.item_remove(item["id"])


class TestItemStats:
    def test_stats_for_domain(self, fitness_domain):
        stats = db.item_stats("fitness")
        assert isinstance(stats, dict)
        assert stats["domain"] == "fitness"
        assert stats["total"] >= 1
        assert isinstance(stats["by_type"], dict)
        assert isinstance(stats["by_status"], dict)

    def test_stats_empty_domain(self):
        dom = db.domain_add(name="stats_empty_test", description="empty")
        stats = db.item_stats("stats_empty_test")
        assert stats["total"] == 0
        db.domain_remove("stats_empty_test")

    def test_stats_bad_domain(self):
        with pytest.raises(ValueError):
            db.item_stats("nonexistent_domain")
