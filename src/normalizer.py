"""食材名 RAG ノーマライザー — ハイブリッド2ステップ検索。

## RAGパターンの適用

```
[Index: オフライン]
  food_master_data.py の食材マスタ
    └─ build_embeddings() → OpenAI text-embedding-3-small → SQLite (food_embeddings)

[Retrieve: 実行時]
  Gemini が返した食材名
    │
    ├─ Step1: ファジーマッチ (difflib.SequenceMatcher)
    │    正規名 + 別名すべてと比較 → スコア >= 0.72 で採用
    │    API 不要・高速なため、まずこちらを試みる
    │
    └─ Step2: 埋め込みベクトル検索 (OpenAI embedding)
         入力をベクトル化 → SQLite保存ベクトルとcos類似度比較
         スコア >= 0.80 で採用（意味的類似に強い）

[Augment]
  vision.py の Gemini プロンプトに正規名リストを注入
  → Gemini が出力段階で正規名に揃えやすくなる
```
"""

import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher

from . import db as _db


@dataclass
class NormalizeResult:
    """normalize() の返り値。"""
    canonical: str               # 正規化後の食材名
    category: str                # カテゴリ（空文字 = 未知）
    shelf_life_days: int | None  # 標準冷蔵保存日数（None = 長期保存 or 未登録）
    method: str                  # "fuzzy" | "embedding" | "none"
    score: float                 # 類似度スコア 0.0〜1.0
    changed: bool                # 入力と canonical が異なるとき True


_FUZZY_THRESHOLD = 0.72   # ファジーマッチ採用の最低スコア
_EMBED_THRESHOLD = 0.80   # コサイン類似度の採用最低スコア
_EMBED_MODEL     = "text-embedding-3-small"


class Normalizer:
    """ハイブリッドRAGノーマライザー。

    生成時にSQLiteから食材マスタを読み込む（遅延ロード）。
    埋め込みキャッシュも最初のembedding検索時に一括取得する。
    """

    def __init__(self) -> None:
        self._master: list[dict] | None = None
        self._embeddings: dict[str, "np.ndarray"] | None = None

    # ── マスタ・埋め込みのロード ──────────────────────────────────────────────

    def _load_master(self) -> list[dict]:
        if self._master is None:
            self._master = _db.get_food_master()
        return self._master

    def _load_embeddings(self) -> dict[str, "np.ndarray"]:
        if self._embeddings is None:
            import numpy as np
            rows = _db.get_food_embeddings()
            self._embeddings = {
                r["canonical"]: np.array(json.loads(r["embedding"]), dtype=np.float32)
                for r in rows
            }
        return self._embeddings

    # ── Step1: ファジーマッチ ────────────────────────────────────────────────

    @staticmethod
    def _fuzzy_score(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _best_fuzzy(self, name: str) -> tuple[dict | None, float]:
        best_item: dict | None = None
        best_score = 0.0
        for item in self._load_master():
            candidates = [item["canonical"]] + item.get("aliases", [])
            for cand in candidates:
                s = self._fuzzy_score(name, cand)
                if s > best_score:
                    best_score = s
                    best_item = item
        return best_item, best_score

    # ── Step2: 埋め込みベクトル検索 ──────────────────────────────────────────

    @staticmethod
    def _embed(text: str) -> "np.ndarray":
        import numpy as np
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.embeddings.create(model=_EMBED_MODEL, input=[text])
        return np.array(resp.data[0].embedding, dtype=np.float32)

    @staticmethod
    def _cosine(a: "np.ndarray", b: "np.ndarray") -> float:
        import numpy as np
        d = float(np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / d) if d > 0 else 0.0

    def _best_embed(self, name: str) -> tuple[dict | None, float]:
        embeddings = self._load_embeddings()
        if not embeddings:
            return None, 0.0
        query_vec = self._embed(name)
        best_canonical: str | None = None
        best_score = 0.0
        for canonical, vec in embeddings.items():
            s = self._cosine(query_vec, vec)
            if s > best_score:
                best_score = s
                best_canonical = canonical
        if best_canonical is None:
            return None, 0.0
        item = next((m for m in self._load_master() if m["canonical"] == best_canonical), None)
        return item, best_score

    # ── 公開 API ─────────────────────────────────────────────────────────────

    def normalize(self, name: str) -> NormalizeResult:
        """食材名を正規名に変換する。

        Step1（ファジー）→ Step2（embedding）→ 変換なし の優先順。
        """
        # Step1: ファジーマッチ
        item, score = self._best_fuzzy(name)
        if item is not None and score >= _FUZZY_THRESHOLD:
            return NormalizeResult(
                canonical=item["canonical"],
                category=item.get("category", ""),
                shelf_life_days=item.get("shelf_life_days"),
                method="fuzzy",
                score=score,
                changed=(name != item["canonical"]),
            )

        # Step2: 埋め込みベクトル検索（OPENAI_API_KEY がある場合のみ）
        if os.environ.get("OPENAI_API_KEY"):
            try:
                item, score = self._best_embed(name)
                if item is not None and score >= _EMBED_THRESHOLD:
                    return NormalizeResult(
                        canonical=item["canonical"],
                        category=item.get("category", ""),
                        shelf_life_days=item.get("shelf_life_days"),
                        method="embedding",
                        score=score,
                        changed=(name != item["canonical"]),
                    )
            except Exception as e:
                print(f"[normalizer] embedding エラー（スキップ）: {e}")

        # Step3: 変換なし
        return NormalizeResult(
            canonical=name,
            category="",
            shelf_life_days=None,
            method="none",
            score=0.0,
            changed=False,
        )

    def normalize_item(self, item: dict) -> dict:
        """{"name", "quantity", "unit"} を正規化して返す（元のdictは変更しない）。"""
        result = self.normalize(item["name"])
        out = dict(item)
        out["name"] = result.canonical
        if result.category and not item.get("category"):
            out["category"] = result.category
        out["_normalize_method"] = result.method
        out["_normalize_score"] = round(result.score, 3)
        return out

    def reset_cache(self) -> None:
        """マスタ・埋め込みキャッシュをクリア（テスト用 / 再構築後に呼ぶ）。"""
        self._master = None
        self._embeddings = None


# ── グローバルシングルトン ────────────────────────────────────────────────────

_instance: Normalizer | None = None


def get_normalizer() -> Normalizer:
    """グローバルNormalizerを返す（遅延初期化）。"""
    global _instance
    if _instance is None:
        _instance = Normalizer()
    return _instance


# ── 索引構築（Index phase） ───────────────────────────────────────────────────

def build_embeddings(force: bool = False) -> int:
    """食材マスタの埋め込みを生成してSQLiteに保存する（RAGのIndex phase）。

    各食材の正規名 + 別名を結合したテキストをベクトル化することで、
    別名経由のクエリでも高精度な類似検索が可能になる。

    例: "玉ねぎ / たまねぎ / オニオン / 新玉ねぎ / 淡路玉ねぎ"

    Args:
        force: True のとき既存の埋め込みをすべて上書きする

    Returns:
        生成・保存した件数
    """
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv()

    master = _db.get_food_master()
    if not master:
        print("[normalizer] 食材マスタが空です。先に build_master.py を実行してください。")
        return 0

    existing = {r["canonical"] for r in _db.get_food_embeddings()} if not force else set()
    to_embed = [m for m in master if m["canonical"] not in existing]
    if not to_embed:
        print(f"[normalizer] 全{len(existing)}件は埋め込み済みです。")
        return 0

    # 正規名 + 別名を "/" 区切りで結合（埋め込みに別名の意味を乗せる）
    texts = [
        " / ".join([m["canonical"]] + m.get("aliases", []))
        for m in to_embed
    ]

    print(f"[normalizer] {len(to_embed)} 件の埋め込みを生成中…")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.embeddings.create(model=_EMBED_MODEL, input=texts)

    for m, emb_obj in zip(to_embed, resp.data):
        _db.save_food_embedding(
            canonical=m["canonical"],
            embedding=emb_obj.embedding,
            model=_EMBED_MODEL,
        )
    print(f"[normalizer] {len(to_embed)} 件を保存しました。")

    global _instance
    if _instance is not None:
        _instance.reset_cache()

    return len(to_embed)


def get_canonical_names() -> list[str]:
    """食材マスタの全正規名リストを返す（Geminiプロンプト注入用）。"""
    return [m["canonical"] for m in _db.get_food_master()]
