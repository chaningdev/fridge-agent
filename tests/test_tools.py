"""Unit tests for tools.py — Gemini/OpenAI calls are mocked."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import src.db as db
import src.tools as tools
import src.vision as vision


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


# --- parse_receipt_tool ---

def test_parse_receipt_tool_adds_inventory(tmp_path, monkeypatch):
    fake_image = tmp_path / "receipt.jpg"
    fake_image.write_bytes(b"fake")

    mock_items = [
        {"name": "牛乳", "quantity": 1, "unit": "L"},
        {"name": "卵", "quantity": 6, "unit": "個"},
    ]
    monkeypatch.setattr(vision, "parse_receipt", lambda _: mock_items)

    result = tools.parse_receipt_tool(str(fake_image))

    assert result["count"] == 2
    inv = {i["name"]: i for i in db.get_inventory()}
    assert inv["牛乳"]["quantity"] == 1
    assert inv["卵"]["quantity"] == 6


def test_parse_receipt_tool_missing_file():
    result = tools.parse_receipt_tool("/nonexistent/receipt.jpg")
    assert "error" in result


# --- recognize_dish_tool ---

def test_recognize_dish_tool_consumes_inventory(tmp_path, monkeypatch):
    db.upsert_item("鶏肉", 300, "g")
    db.upsert_item("玉ねぎ", 2, "個")

    fake_image = tmp_path / "dish.jpg"
    fake_image.write_bytes(b"fake")

    monkeypatch.setattr(vision, "recognize_dish", lambda _: [
        {"name": "鶏肉", "quantity": 200, "unit": "g"},
        {"name": "玉ねぎ", "quantity": 1, "unit": "個"},
    ])

    result = tools.recognize_dish_tool(str(fake_image))

    assert len(result["consumed"]) == 2
    assert result["not_found"] == []
    inv = {i["name"]: i for i in db.get_inventory()}
    assert inv["鶏肉"]["quantity"] == 100
    assert inv["玉ねぎ"]["quantity"] == 1


def test_recognize_dish_tool_item_not_in_inventory(tmp_path, monkeypatch):
    fake_image = tmp_path / "dish.jpg"
    fake_image.write_bytes(b"fake")

    monkeypatch.setattr(vision, "recognize_dish", lambda _: [
        {"name": "存在しない食材", "quantity": 1, "unit": "個"},
    ])

    result = tools.recognize_dish_tool(str(fake_image))
    assert len(result["not_found"]) == 1
    assert result["consumed"] == []


# --- update_inventory_tool ---

def test_update_inventory_add():
    result = tools.update_inventory_tool("トマト", 3, "個", action="add")
    assert result["action"] == "add"
    inv = {i["name"]: i for i in db.get_inventory()}
    assert inv["トマト"]["quantity"] == 3


def test_update_inventory_consume():
    db.upsert_item("にんじん", 5, "本")
    result = tools.update_inventory_tool("にんじん", 2, action="consume")
    assert result["success"] is True
    inv = {i["name"]: i for i in db.get_inventory()}
    assert inv["にんじん"]["quantity"] == 3


# --- check_inventory_tool ---

def test_check_inventory():
    db.upsert_item("豆腐", 1, "丁")
    result = tools.check_inventory_tool()
    assert result["count"] == 1
    assert result["inventory"][0]["name"] == "豆腐"


# --- shopping_list_tool ---

def test_shopping_list_threshold():
    db.upsert_item("バター", 0.5, "個")
    db.upsert_item("チーズ", 3, "個")
    result = tools.shopping_list_tool(threshold=1.0)
    names = [i["name"] for i in result["shopping_list"]]
    assert "バター" in names
    assert "チーズ" not in names
