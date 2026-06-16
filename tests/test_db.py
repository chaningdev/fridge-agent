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


# ── 賞味期限・カテゴリ ────────────────────────────────────────────────────────

def test_upsert_with_category_and_expiry():
    db.upsert_item("牛乳", 1, "L", category="乳製品", expires_at="2026-06-20")
    items = {i["name"]: i for i in db.get_inventory()}
    assert items["牛乳"]["category"] == "乳製品"
    assert items["牛乳"]["expires_at"] == "2026-06-20"


def test_category_not_overwritten_on_restock():
    db.upsert_item("卵", 6, "個", category="卵", expires_at="2026-06-25")
    db.upsert_item("卵", 6, "個")  # category/expires_at 省略で再入荷
    items = {i["name"]: i for i in db.get_inventory()}
    assert items["卵"]["category"] == "卵"        # 上書きされない
    assert items["卵"]["expires_at"] == "2026-06-25"


def test_get_expiring_items():
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=2)).isoformat()
    far  = (date.today() + timedelta(days=30)).isoformat()
    db.upsert_item("ヨーグルト", 1, "個", expires_at=soon)
    db.upsert_item("チーズ",     1, "個", expires_at=far)
    expiring = db.get_expiring_items(days=3)
    names = [i["name"] for i in expiring]
    assert "ヨーグルト" in names
    assert "チーズ" not in names


def test_get_expiring_includes_expired():
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db.upsert_item("期限切れ品", 1, "個", expires_at=yesterday)
    expiring = db.get_expiring_items(days=0)
    names = [i["name"] for i in expiring]
    assert "期限切れ品" in names


def test_inventory_sorted_by_expiry_first():
    from datetime import date, timedelta
    db.upsert_item("A食材", 1, "個", expires_at=(date.today() + timedelta(days=1)).isoformat())
    db.upsert_item("Z食材", 1, "個")  # 期限なし
    items = db.get_inventory()
    names = [i["name"] for i in items]
    assert names.index("A食材") < names.index("Z食材")  # 期限あり食材が先頭
