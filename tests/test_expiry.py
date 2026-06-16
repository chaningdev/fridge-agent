"""Tests for expiry_master and db auto-fill integration."""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import src.db as db
from src.expiry_master import get_default_days, get_default_expiry


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


# ── expiry_master: get_default_days ──────────────────────────────────────────

def test_known_item_returns_days():
    assert get_default_days("鶏もも肉") == 3
    assert get_default_days("牛乳") == 7
    assert get_default_days("卵") == 21
    assert get_default_days("玉ねぎ") == 30
    assert get_default_days("もやし") == 2


def test_unknown_item_returns_none():
    assert get_default_days("砂糖") is None
    assert get_default_days("こんにゃく") is None
    assert get_default_days("") is None


def test_partial_name_matches():
    # 「鶏もも肉 200g」のように単位が付いていても一致する
    assert get_default_days("鶏もも肉 200g") == 3
    assert get_default_days("カットキャベツ") == 7


# ── expiry_master: get_default_expiry ────────────────────────────────────────

def test_expiry_returns_future_date():
    result = get_default_expiry("牛乳")
    assert result is not None
    expected = (date.today() + timedelta(days=7)).isoformat()
    assert result == expected


def test_expiry_unknown_returns_none():
    assert get_default_expiry("砂糖") is None


# ── db.upsert_item: 自動補完 ──────────────────────────────────────────────────

def test_auto_fill_applied_when_expires_at_none():
    db.upsert_item("鶏もも肉", 300, "g")
    items = {i["name"]: i for i in db.get_inventory()}
    expected = (date.today() + timedelta(days=3)).isoformat()
    assert items["鶏もも肉"]["expires_at"] == expected


def test_explicit_expiry_not_overridden():
    manual_date = "2099-12-31"
    db.upsert_item("卵", 6, "個", expires_at=manual_date)
    items = {i["name"]: i for i in db.get_inventory()}
    assert items["卵"]["expires_at"] == manual_date


def test_unknown_item_stays_null():
    db.upsert_item("砂糖", 500, "g")
    items = {i["name"]: i for i in db.get_inventory()}
    assert items["砂糖"]["expires_at"] is None


def test_auto_fill_returns_expiry_value():
    result = db.upsert_item("牛乳", 1, "L")
    expected = (date.today() + timedelta(days=7)).isoformat()
    assert result == expected


def test_explicit_expiry_return_value():
    manual_date = "2099-01-01"
    result = db.upsert_item("卵", 6, "個", expires_at=manual_date)
    assert result == manual_date


def test_unknown_item_return_value():
    result = db.upsert_item("砂糖", 500, "g")
    assert result is None


# ── 具体的な食材でカテゴリをまとめて確認 ────────────────────────────────────

@pytest.mark.parametrize("name,expected_days", [
    ("挽肉",       1),
    ("サーモン",   2),
    ("豆腐",       4),
    ("ほうれん草", 4),
    ("もやし",     2),
    ("にんじん",   14),
    ("じゃがいも", 21),
    ("バナナ",     5),
    ("いちご",     3),
    ("ヨーグルト", 14),
    ("バター",     30),
])
def test_parametrized_shelf_life(name, expected_days):
    assert get_default_days(name) == expected_days
