"""食材名 RAG ノーマライザーのテスト。

テスト戦略:
  - ファジーマッチは食材マスタDBに依存するため、テスト用フィクスチャで
    一時DBを構築してからテストを実行する。
  - 埋め込み検索は OPENAI_API_KEY を要するため、キーがない環境ではスキップ。
"""

import os
import json
import pytest

from src import db
from src.normalizer import Normalizer, NormalizeResult, get_canonical_names


# ── テスト用フィクスチャ ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """テスト毎に一時DBを使い、食材マスタを投入する。"""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.build_food_master()
    yield


@pytest.fixture
def normalizer():
    """テスト用 Normalizer（毎回新規インスタンス）。"""
    return Normalizer()


# ── ファジーマッチ ────────────────────────────────────────────────────────────

def test_exact_canonical_name(normalizer):
    """正規名そのままの入力 → 変換なし・スコア1.0。"""
    result = normalizer.normalize("玉ねぎ")
    assert result.canonical == "玉ねぎ"
    assert result.score == pytest.approx(1.0)
    assert result.method == "fuzzy"
    assert not result.changed


def test_alias_to_canonical(normalizer):
    """別名 → 正規名に変換される。"""
    result = normalizer.normalize("オニオン")
    assert result.canonical == "玉ねぎ"
    assert result.method == "fuzzy"
    assert result.changed


def test_alias_kana_to_canonical(normalizer):
    """ひらがな別名 → 正規名。"""
    result = normalizer.normalize("たまねぎ")
    assert result.canonical == "玉ねぎ"
    assert result.method == "fuzzy"


def test_partial_name_prefix(normalizer):
    """産地付き商品名 → 正規名（ファジーマッチが産地を無視して一致）。"""
    result = normalizer.normalize("淡路たまねぎ")
    assert result.canonical == "玉ねぎ"
    assert result.method == "fuzzy"


def test_category_returned(normalizer):
    """正規化時にカテゴリが返される。"""
    result = normalizer.normalize("鶏もも肉")
    assert result.category == "肉・魚"


def test_shelf_life_days_returned(normalizer):
    """正規化時に標準保存日数が返される。"""
    result = normalizer.normalize("卵")
    assert result.shelf_life_days == 21


def test_unknown_item_returns_none_method(normalizer):
    """マスタに存在しない食材 → method='none'・canonical は入力そのまま。"""
    result = normalizer.normalize("プロテインバー")
    assert result.method == "none"
    assert result.canonical == "プロテインバー"
    assert not result.changed


@pytest.mark.parametrize("alias,canonical", [
    ("チキンもも",  "鶏もも肉"),
    ("ポークバラ",  "豚バラ肉"),
    ("ほうれんそう", "ほうれん草"),
    ("えのきだけ",  "えのき"),
    ("ぶなしめじ",  "しめじ"),
    ("鮭",          "サーモン"),
    ("えび",        "エビ"),
])
def test_alias_normalization(normalizer, alias, canonical):
    """複数の別名が正規名に正規化されることを確認。"""
    result = normalizer.normalize(alias)
    assert result.canonical == canonical, (
        f"'{alias}' → '{canonical}' を期待したが '{result.canonical}' (score={result.score:.2f}) だった"
    )


# ── normalize_item ────────────────────────────────────────────────────────────

def test_normalize_item_sets_name(normalizer):
    """normalize_item: name フィールドが正規化される。"""
    item = {"name": "オニオン", "quantity": 2, "unit": "個"}
    out = normalizer.normalize_item(item)
    assert out["name"] == "玉ねぎ"
    assert out["quantity"] == 2  # 数量は変わらない


def test_normalize_item_adds_category(normalizer):
    """normalize_item: category が空の場合はマスタから補完される。"""
    item = {"name": "にんじん", "quantity": 3, "unit": "本"}
    out = normalizer.normalize_item(item)
    assert out["category"] == "野菜"


def test_normalize_item_keeps_existing_category(normalizer):
    """normalize_item: category が既にある場合は上書きしない。"""
    item = {"name": "にんじん", "quantity": 3, "unit": "本", "category": "野菜カスタム"}
    out = normalizer.normalize_item(item)
    assert out["category"] == "野菜カスタム"


def test_normalize_item_adds_metadata(normalizer):
    """normalize_item: _normalize_method / _normalize_score フィールドが付与される。"""
    item = {"name": "玉ねぎ", "quantity": 1, "unit": "個"}
    out = normalizer.normalize_item(item)
    assert "_normalize_method" in out
    assert "_normalize_score" in out


def test_normalize_item_does_not_mutate_original(normalizer):
    """normalize_item: 元のdictを変更しない（副作用なし）。"""
    item = {"name": "オニオン", "quantity": 1, "unit": "個"}
    normalizer.normalize_item(item)
    assert item["name"] == "オニオン"


# ── get_canonical_names ───────────────────────────────────────────────────────

def test_get_canonical_names():
    """get_canonical_names: 正規名リストが返される。"""
    names = get_canonical_names()
    assert isinstance(names, list)
    assert "玉ねぎ" in names
    assert "鶏もも肉" in names
    assert len(names) >= 50  # 食材マスタに十分な件数があること


# ── 埋め込みキャッシュリセット ────────────────────────────────────────────────

def test_reset_cache(normalizer):
    """reset_cache 後もマスタが再ロードされる。"""
    _ = normalizer.normalize("玉ねぎ")   # キャッシュを温める
    normalizer.reset_cache()
    result = normalizer.normalize("玉ねぎ")
    assert result.canonical == "玉ねぎ"


# ── 埋め込み検索（OPENAI_API_KEY が必要） ─────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY が設定されていないためスキップ"
)
def test_embedding_search_semantic(normalizer, tmp_path, monkeypatch):
    """埋め込み検索: ファジーでは届かない意味的類似が正規化される。"""
    from src.normalizer import build_embeddings
    build_embeddings()

    # "ポテト" はファジーだと "じゃがいも" に届きにくいが、embedding なら届く
    result = normalizer.normalize("ポテト")
    assert result.canonical == "じゃがいも"
    assert result.method in ("fuzzy", "embedding")
