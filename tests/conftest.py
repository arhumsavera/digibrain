"""Shared fixtures for digibrain tests.

Every test session gets a fresh temporary SQLite database.
The db module's connection cache and DB_PATH are patched so all
db.* calls hit the temp DB automatically — no monkeypatching needed
inside individual tests.
"""
from __future__ import annotations

import json

import pytest

import tools.applyops.db as db


@pytest.fixture(scope="session", autouse=True)
def test_db(tmp_path_factory):
    """Create a temp DB for the entire test session, patch db module to use it."""
    tmp_dir = tmp_path_factory.mktemp("applyops")
    db_path = tmp_dir / "test.db"

    # Patch before any connection is made
    original_path = db.DB_PATH
    original_cache = db._conn_cache

    db.DB_PATH = db_path
    db._conn_cache = None

    yield db_path

    # Teardown: close connection, restore originals
    if db._conn_cache is not None:
        db._conn_cache.close()
    db._conn_cache = original_cache
    db.DB_PATH = original_path


@pytest.fixture(scope="session")
def conn(test_db):
    """Get the shared DB connection (same one cached by db module)."""
    return db.get_conn()


# -- Reusable domain fixtures (session-scoped, created once) --

@pytest.fixture(scope="session")
def fitness_domain():
    return db.domain_add(
        name="fitness",
        description="Workout and health tracking",
        keywords=json.dumps(["workout", "gym", "exercise", "fitness", "run", "lift", "cardio"]),
        icon="muscle",
    )


@pytest.fixture(scope="session")
def todos_domain():
    return db.domain_add(
        name="todos",
        description="General task list",
        keywords=json.dumps(["todo", "task", "reminder", "deadline"]),
    )


@pytest.fixture(scope="session")
def reading_domain():
    return db.domain_add(
        name="reading",
        description="Book and article tracking",
        keywords=json.dumps(["book", "read", "article", "paper"]),
    )
