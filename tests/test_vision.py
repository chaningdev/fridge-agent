"""Unit tests for vision._parse_json_response and router."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.vision import _parse_json_response
from src.router import route, TaskType


# ── _parse_json_response ────────────────────────────────────────────────────

def test_parse_plain_json():
    raw = '[{"name": "卵", "quantity": 6, "unit": "個"}]'
    result = _parse_json_response(raw)
    assert result[0]["name"] == "卵"
    assert result[0]["quantity"] == 6.0


def test_parse_json_with_code_fence():
    raw = '```json\n[{"name": "牛乳", "quantity": 1, "unit": "L"}]\n```'
    result = _parse_json_response(raw)
    assert result[0]["name"] == "牛乳"


def test_parse_json_fence_no_lang():
    raw = '```\n[{"name": "豆腐", "quantity": 1, "unit": "丁"}]\n```'
    result = _parse_json_response(raw)
    assert result[0]["unit"] == "丁"


def test_parse_json_embedded_in_text():
    raw = 'こちらが結果です:\n[{"name": "にんじん", "quantity": 2, "unit": "本"}]\n以上です。'
    result = _parse_json_response(raw)
    assert result[0]["name"] == "にんじん"


def test_parse_normalizes_missing_unit():
    raw = '[{"name": "りんご", "quantity": 3}]'
    result = _parse_json_response(raw)
    assert result[0]["unit"] == "個"


def test_parse_normalizes_missing_quantity():
    raw = '[{"name": "バナナ", "unit": "本"}]'
    result = _parse_json_response(raw)
    assert result[0]["quantity"] == 1.0


def test_parse_multiple_items():
    raw = '''[
      {"name": "鶏肉", "quantity": 200, "unit": "g"},
      {"name": "玉ねぎ", "quantity": 1, "unit": "個"},
      {"name": "じゃがいも", "quantity": 2, "unit": "個"}
    ]'''
    result = _parse_json_response(raw)
    assert len(result) == 3
    assert result[1]["name"] == "玉ねぎ"


def test_parse_invalid_json_raises():
    with pytest.raises(Exception):
        _parse_json_response("これはJSONではありません")


# ── router ──────────────────────────────────────────────────────────────────

def test_route_receipt_by_keyword_and_image():
    r = route("レシートを読み込んで", image_path="receipt.jpg")
    assert r.task_type == TaskType.PARSE_RECEIPT
    assert r.model_backend == "gemini"
    assert r.kwargs["image_path"] == "receipt.jpg"


def test_route_dish_image_no_keyword():
    r = route("これ何の料理かな", image_path="food.png")
    assert r.task_type == TaskType.RECOGNIZE_DISH
    assert r.model_backend == "gemini"


def test_route_image_path_in_text():
    r = route("この画像を解析して /tmp/dish.jpg")
    assert r.task_type == TaskType.RECOGNIZE_DISH
    assert r.kwargs["image_path"] == "/tmp/dish.jpg"


def test_route_receipt_path_in_text():
    r = route("レシート /tmp/receipt.png を読んで")
    assert r.task_type == TaskType.PARSE_RECEIPT


def test_route_check_inventory():
    r = route("今の在庫を確認して")
    assert r.task_type == TaskType.CHECK_INVENTORY
    assert r.model_backend == "sqlite"


def test_route_shopping_list():
    r = route("買い物リストを作って")
    assert r.task_type == TaskType.SHOPPING_LIST
    assert r.model_backend == "sqlite"


def test_route_suggest_recipe():
    r = route("今ある食材でレシピを提案して")
    assert r.task_type == TaskType.SUGGEST_RECIPE
    assert r.model_backend == "openai"


def test_route_add_inventory():
    r = route("トマトを3個追加", name="トマト", quantity=3, unit="個")
    assert r.task_type == TaskType.UPDATE_INVENTORY
    assert r.kwargs["action"] == "add"


def test_route_consume_inventory():
    r = route("卵を2個使った", name="卵", quantity=2)
    assert r.task_type == TaskType.UPDATE_INVENTORY
    assert r.kwargs["action"] == "consume"


def test_route_unknown():
    r = route("こんにちは")
    assert r.task_type == TaskType.UNKNOWN
