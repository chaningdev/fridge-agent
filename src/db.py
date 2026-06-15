"""SQLite-backed inventory store for Fridge Agent."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fridge.db"


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
    """Create tables if they do not yet exist."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT    NOT NULL UNIQUE,
                quantity  REAL    NOT NULL DEFAULT 0,
                unit      TEXT    NOT NULL DEFAULT '',
                updated_at TEXT   NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                action     TEXT    NOT NULL,  -- 'add' | 'consume'
                item_name  TEXT    NOT NULL,
                quantity   REAL    NOT NULL,
                unit       TEXT    NOT NULL DEFAULT '',
                source     TEXT,              -- 'receipt' | 'dish' | 'manual'
                created_at TEXT    NOT NULL
            );
        """)


def upsert_item(name: str, quantity: float, unit: str = "", source: str = "manual") -> None:
    """Add quantity to an existing item or insert a new one."""
    now = datetime.now().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO inventory (name, quantity, unit, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                quantity   = quantity + excluded.quantity,
                unit       = excluded.unit,
                updated_at = excluded.updated_at
        """, (name, quantity, unit, now))
        con.execute("""
            INSERT INTO history (action, item_name, quantity, unit, source, created_at)
            VALUES ('add', ?, ?, ?, ?, ?)
        """, (name, quantity, unit, source, now))


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
    """Return all items with quantity > 0."""
    with _conn() as con:
        rows = con.execute(
            "SELECT name, quantity, unit, updated_at FROM inventory WHERE quantity > 0 ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(limit: int = 50) -> list[dict]:
    """Return recent history entries."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("DB initialized:", DB_PATH)
