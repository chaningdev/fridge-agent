"""Interactive CLI demo for Fridge Agent.

Run: python demo.py
"""

import io
import sys
from pathlib import Path

# Windows コンソールの文字化け対策
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp932", "cp936", "gbk"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from src import db
from src import tools

db.init_db()


def _hr():
    print("-" * 40)


def _show_inventory():
    items = db.get_inventory()
    if not items:
        print("  (在庫なし)")
        return
    for i in items:
        print(f"  {i['name']:<12} {i['quantity']}{i['unit']}")


def _show_history():
    rows = db.get_history(limit=10)
    if not rows:
        print("  (履歴なし)")
        return
    for r in rows:
        print(f"  [{r['action']}] {r['item_name']} {r['quantity']}{r['unit']}  ({r['source']})  {r['created_at'][:19]}")


MENU = """
========= Fridge Agent Demo =========
 1. 在庫を確認する
 2. 食材を追加する
 3. 食材を消費する
 4. 買い物リストを見る
 5. 操作履歴を見る
 6. レシート画像を読み込む  [Gemini必要]
 7. 料理写真から消費する    [Gemini必要]
 8. 献立を提案する          [OpenAI必要]
 9. デモデータを投入する
 0. 終了
=====================================
"""


def cmd_check():
    _hr()
    print("【在庫一覧】")
    result = tools.check_inventory_tool()
    _show_inventory()
    print(f"  合計 {result['count']} 種類")
    _hr()


def cmd_add():
    name = input("食材名: ").strip()
    if not name:
        return
    try:
        qty = float(input("数量: ").strip() or "1")
    except ValueError:
        qty = 1.0
    unit = input("単位（個/g/ml/本 など）: ").strip() or "個"
    result = tools.update_inventory_tool(name, qty, unit, action="add")
    print(f"  ✓ {result['name']} {result['quantity']}{result['unit']} を追加しました")


def cmd_consume():
    _show_inventory()
    name = input("消費する食材名: ").strip()
    if not name:
        return
    try:
        qty = float(input("数量: ").strip() or "1")
    except ValueError:
        qty = 1.0
    result = tools.update_inventory_tool(name, qty, action="consume")
    if result.get("success"):
        print(f"  ✓ {name} {qty} を消費しました")
    else:
        print(f"  ✗ '{name}' が在庫に見つかりません")


def cmd_shopping():
    try:
        thr = float(input("閾値（この数量以下を表示, デフォルト1）: ").strip() or "1")
    except ValueError:
        thr = 1.0
    result = tools.shopping_list_tool(threshold=thr)
    _hr()
    print(f"【買い物リスト】（{thr} 以下）")
    if not result["shopping_list"]:
        print("  不足している食材はありません")
    for i in result["shopping_list"]:
        print(f"  {i['name']:<12} 残り {i['quantity']}{i['unit']}")
    _hr()


def cmd_history():
    _hr()
    print("【操作履歴（直近10件）】")
    _show_history()
    _hr()


def cmd_receipt():
    path = input("レシート画像のパス: ").strip()
    if not path:
        return
    print("  Gemini に送信中...")
    result = tools.parse_receipt_tool(path)
    if "error" in result:
        print(f"  ✗ {result['error']}")
        return
    print(f"  ✓ {result['count']} 件の食材を在庫に追加しました:")
    for item in result["added"]:
        print(f"    - {item['name']} {item['quantity']}{item['unit']}")


def cmd_dish():
    path = input("料理写真のパス: ").strip()
    if not path:
        return
    print("  Gemini に送信中...")
    result = tools.recognize_dish_tool(path)
    if "error" in result:
        print(f"  ✗ {result['error']}")
        return
    print(f"  ✓ 消費: {len(result['consumed'])} 種類")
    for i in result["consumed"]:
        print(f"    - {i['name']} {i['quantity']}{i['unit']}")
    if result["not_found"]:
        print(f"  ! 在庫にない食材（スキップ）: {[i['name'] for i in result['not_found']]}")


def cmd_recipe():
    print("  OpenAI に送信中...")
    result = tools.suggest_recipe_tool()
    if "error" in result:
        print(f"  ✗ {result['error']}")
        return
    _hr()
    print("【献立提案】")
    print(result["suggestions"])
    _hr()


def cmd_seed():
    seeds = [
        ("卵", 6, "個"), ("牛乳", 1, "L"), ("鶏もも肉", 300, "g"),
        ("玉ねぎ", 2, "個"), ("にんじん", 1, "本"), ("じゃがいも", 3, "個"),
        ("豆腐", 1, "丁"), ("ほうれん草", 0.5, "袋"),
    ]
    for name, qty, unit in seeds:
        db.upsert_item(name, qty, unit, source="manual")
    print(f"  ✓ {len(seeds)} 種類のデモデータを投入しました")
    _show_inventory()


COMMANDS = {
    "1": cmd_check,
    "2": cmd_add,
    "3": cmd_consume,
    "4": cmd_shopping,
    "5": cmd_history,
    "6": cmd_receipt,
    "7": cmd_dish,
    "8": cmd_recipe,
    "9": cmd_seed,
}


def main():
    print(MENU)
    while True:
        try:
            choice = input("選択 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n終了します")
            break

        if choice == "0":
            print("終了します")
            break

        cmd = COMMANDS.get(choice)
        if cmd:
            try:
                cmd()
            except Exception as e:
                print(f"  [ERROR] {e}")
        else:
            print("  0〜9 で選択してください")

        print()


if __name__ == "__main__":
    main()
