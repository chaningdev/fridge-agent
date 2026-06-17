"""SQLite-backed inventory store for Fridge Agent."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from .expiry_master import get_default_expiry

DB_PATH = Path(__file__).parent.parent / "fridge.db"

CATEGORIES = ["", "肉・魚", "野菜", "果物", "乳製品", "卵", "穀物", "調味料", "飲み物", "完成品", "その他"]

# 完成品カテゴリ: お菓子・カップ麺・レトルト食品など単体で食べる加工食品
# 献立提案・消費推定ではこのカテゴリを除外する
READY_FOOD_CATEGORY = "完成品"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables and run column migrations."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                quantity    REAL    NOT NULL DEFAULT 0,
                unit        TEXT    NOT NULL DEFAULT '',
                updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT    NOT NULL,
                item_name   TEXT    NOT NULL,
                quantity    REAL    NOT NULL,
                unit        TEXT    NOT NULL DEFAULT '',
                source      TEXT,
                created_at  TEXT    NOT NULL
            );

            -- RAG用: 食材マスタ（正規名・別名・カテゴリ・標準保存日数）
            CREATE TABLE IF NOT EXISTS food_master (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical       TEXT    NOT NULL UNIQUE,
                aliases         TEXT    NOT NULL DEFAULT '[]',
                category        TEXT    NOT NULL DEFAULT '',
                shelf_life_days INTEGER,
                updated_at      TEXT    NOT NULL
            );

            -- RAG用: 食材マスタの埋め込みベクトル（text-embedding-3-small）
            CREATE TABLE IF NOT EXISTS food_embeddings (
                canonical   TEXT PRIMARY KEY,
                embedding   TEXT NOT NULL,
                model       TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
        """)
        # マイグレーション: 既存DBに新カラムを追加（すでにあればスキップ）
        for ddl in [
            "ALTER TABLE inventory ADD COLUMN category   TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE inventory ADD COLUMN expires_at TEXT",
        ]:
            try:
                con.execute(ddl)
            except sqlite3.OperationalError:
                pass  # column already exists


def upsert_item(
    name: str,
    quantity: float,
    unit: str = "",
    source: str = "manual",
    category: str = "",
    expires_at: str | None = None,
) -> str | None:
    """Add quantity to an existing item or insert a new one.

    Returns the expires_at value that was actually stored
    (either the provided value or the auto-filled default).
    """
    user_provided_expiry = expires_at is not None
    if not user_provided_expiry:
        expires_at = get_default_expiry(name)

    now = datetime.now().isoformat()
    with _conn() as con:
        # expires_at の更新ポリシー:
        #   ユーザーが明示的に指定した場合 → 常に上書き
        #   自動補完 or None の場合       → DB に既に値があれば保持（再入荷時に上書きしない）
        if user_provided_expiry:
            expiry_sql = "excluded.expires_at"
        else:
            expiry_sql = "CASE WHEN expires_at IS NULL THEN excluded.expires_at ELSE expires_at END"

        con.execute(f"""
            INSERT INTO inventory (name, quantity, unit, category, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                quantity   = quantity + excluded.quantity,
                unit       = excluded.unit,
                category   = CASE WHEN excluded.category != '' THEN excluded.category ELSE category END,
                expires_at = {expiry_sql},
                updated_at = excluded.updated_at
        """, (name, quantity, unit, category, expires_at, now))
        con.execute("""
            INSERT INTO history (action, item_name, quantity, unit, source, created_at)
            VALUES ('add', ?, ?, ?, ?, ?)
        """, (name, quantity, unit, source, now))
    return expires_at


def consume_item(name: str, quantity: float, source: str = "manual") -> bool:
    """Subtract quantity from inventory. Returns False if item not found."""
    now = datetime.now().isoformat()
    with _conn() as con:
        row = con.execute(
            "SELECT quantity, unit FROM inventory WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return False
        new_qty = max(0.0, row["quantity"] - quantity)
        con.execute(
            "UPDATE inventory SET quantity = ?, updated_at = ? WHERE name = ?",
            (new_qty, now, name),
        )
        con.execute("""
            INSERT INTO history (action, item_name, quantity, unit, source, created_at)
            VALUES ('consume', ?, ?, ?, ?, ?)
        """, (name, quantity, row["unit"], source, now))
    return True


def get_inventory() -> list[dict]:
    """Return all items with quantity > 0, ordered by expiry then name."""
    with _conn() as con:
        rows = con.execute("""
            SELECT name, quantity, unit, category, expires_at, updated_at
            FROM inventory
            WHERE quantity > 0
            ORDER BY
                CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END,
                expires_at,
                name
        """).fetchall()
    return [dict(r) for r in rows]


def get_expiring_items(days: int = 3) -> list[dict]:
    """Return items expiring within `days` days (including already expired)."""
    threshold = (date.today() + timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT name, quantity, unit, category, expires_at
            FROM inventory
            WHERE expires_at IS NOT NULL AND expires_at <= ? AND quantity > 0
            ORDER BY expires_at
        """, (threshold,)).fetchall()
    return [dict(r) for r in rows]


def get_history(limit: int = 50) -> list[dict]:
    """Return recent history entries."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── 食材マスタ（RAG用） ───────────────────────────────────────────────────────

def build_food_master() -> int:
    """food_master_data.py のデータをSQLiteに投入・更新する。

    Returns:
        投入した食材数
    """
    from .food_master_data import FOOD_MASTER
    now = datetime.now().isoformat()
    with _conn() as con:
        for item in FOOD_MASTER:
            con.execute("""
                INSERT INTO food_master (canonical, aliases, category, shelf_life_days, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(canonical) DO UPDATE SET
                    aliases         = excluded.aliases,
                    category        = excluded.category,
                    shelf_life_days = excluded.shelf_life_days,
                    updated_at      = excluded.updated_at
            """, (
                item["canonical"],
                json.dumps(item.get("aliases", []), ensure_ascii=False),
                item.get("category", ""),
                item.get("shelf_life_days"),
                now,
            ))
    return len(FOOD_MASTER)


def get_food_master() -> list[dict]:
    """food_master テーブルの全件を返す（aliases はリストに変換済み）。"""
    with _conn() as con:
        rows = con.execute(
            "SELECT canonical, aliases, category, shelf_life_days FROM food_master ORDER BY canonical"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["aliases"] = json.loads(d["aliases"])
        except (json.JSONDecodeError, TypeError):
            d["aliases"] = []
        result.append(d)
    return result


def save_food_embedding(canonical: str, embedding: list[float], model: str) -> None:
    """埋め込みベクトルをSQLiteに保存（upsert）。"""
    now = datetime.now().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO food_embeddings (canonical, embedding, model, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(canonical) DO UPDATE SET
                embedding  = excluded.embedding,
                model      = excluded.model,
                updated_at = excluded.updated_at
        """, (canonical, json.dumps(embedding), model, now))


def get_food_embeddings() -> list[dict]:
    """food_embeddings テーブルの全件を返す。"""
    with _conn() as con:
        rows = con.execute(
            "SELECT canonical, embedding, model FROM food_embeddings ORDER BY canonical"
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("DB initialized:", DB_PATH)
