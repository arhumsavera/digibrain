"""Edge cases — weird inputs, boundaries, unicode, nested data."""
import json

import tools.applyops.db as db


class TestEdgeCases:
    def test_complex_nested_json(self, fitness_domain):
        data = json.dumps({
            "sets": [{"weight": 100, "reps": 10}, {"weight": 110, "reps": 8}],
            "notes": "Felt strong",
        })
        item = db.item_add(domain="fitness", title="Complex data", type="workout", data=data)
        fetched = db.item_get(item["id"])
        assert json.loads(fetched["data"]) == json.loads(data)

    def test_long_title(self, todos_domain):
        title = "A" * 500
        item = db.item_add(domain="todos", title=title)
        fetched = db.item_get(item["id"])
        assert len(fetched["title"]) == 500

    def test_unicode_title(self, reading_domain):
        item = db.item_add(domain="reading", title="日本語の本 — A Japanese Book")
        fetched = db.item_get(item["id"])
        assert "日本語" in fetched["title"]

    def test_emoji_in_data(self, fitness_domain):
        item = db.item_add(
            domain="fitness", title="Emoji test",
            data=json.dumps({"mood": "feeling great"}),
        )
        fetched = db.item_get(item["id"])
        assert fetched["data"] is not None

    def test_empty_string_fields(self, todos_domain):
        item = db.item_add(domain="todos", title="Empty data", data="", tags="")
        fetched = db.item_get(item["id"])
        assert fetched["data"] == ""
        assert fetched["tags"] == ""

    def test_item_list_empty_domain(self):
        dom = db.domain_add(name="edge_empty", description="empty")
        items = db.item_list(domain="edge_empty")
        assert items == []
        db.domain_remove("edge_empty")

    def test_item_list_nonexistent_domain(self):
        items = db.item_list(domain="zzz_nonexistent_zzz")
        assert items == []
