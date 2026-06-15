"""Basic smoke tests for db.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import os
import pytest
import src.db as db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp file for each test."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


def test_upsert_and_get():
    db.upsert_item("tomato", 3, "個")
    items = db.get_inventory()
    assert any(i["name"] == "tomato" and i["quantity"] == 3 for i in items)


def test_upsert_accumulates():
    db.upsert_item("egg", 6, "個")
    db.upsert_item("egg", 4, "個")
    items = {i["name"]: i for i in db.get_inventory()}
    assert items["egg"]["quantity"] == 10


def test_consume():
    db.upsert_item("milk", 2, "L")
    result = db.consume_item("milk", 1)
    assert result is True
    items = {i["name"]: i for i in db.get_inventory()}
    assert items["milk"]["quantity"] == 1


def test_consume_missing_item():
    result = db.consume_item("nonexistent", 1)
    assert result is False


def test_history_recorded():
    db.upsert_item("carrot", 5, "本", source="receipt")
    db.consume_item("carrot", 2, source="dish")
    history = db.get_history()
    actions = [h["action"] for h in history]
    assert "add" in actions
    assert "consume" in actions
