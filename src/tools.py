"""Tool definitions for Fridge Agent.

Each tool is a plain callable that accepts structured input and returns a dict.
The agent / router calls these directly; they do not depend on each other.
"""

from pathlib import Path

from . import db
from . import vision


def parse_receipt_tool(image_path: str) -> dict:
    """
    レシート画像から食材を抽出して在庫に追加する。

    Args:
        image_path: レシート画像のファイルパス

    Returns:
        {"added": [{"name", "quantity", "unit"}, ...], "count": int}
    """
    if not Path(image_path).exists():
        return {"error": f"File not found: {image_path}"}

    items = vision.parse_receipt(image_path)
    for item in items:
        db.upsert_item(
            name=item["name"],
            quantity=float(item.get("quantity", 1)),
            unit=item.get("unit", "個"),
            source="receipt",
        )
    return {"added": items, "count": len(items)}


def recognize_dish_tool(image_path: str) -> dict:
    """
    料理写真から使用食材を推定して在庫から消費する。

    Args:
        image_path: 料理写真のファイルパス

    Returns:
        {"consumed": [{"name", "quantity", "unit"}, ...], "not_found": [...]}
    """
    if not Path(image_path).exists():
        return {"error": f"File not found: {image_path}"}

    items = vision.recognize_dish(image_path)
    consumed, not_found = [], []
    for item in items:
        ok = db.consume_item(
            name=item["name"],
            quantity=float(item.get("quantity", 1)),
            source="dish",
        )
        (consumed if ok else not_found).append(item)
    return {"consumed": consumed, "not_found": not_found}


def update_inventory_tool(name: str, quantity: float, unit: str = "", action: str = "add") -> dict:
    """
    在庫を手動で追加または消費する。

    Args:
        name: 食材名
        quantity: 数量
        unit: 単位
        action: "add" | "consume"
    """
    if action == "add":
        db.upsert_item(name, quantity, unit, source="manual")
        return {"action": "add", "name": name, "quantity": quantity, "unit": unit}
    elif action == "consume":
        ok = db.consume_item(name, quantity, source="manual")
        return {"action": "consume", "name": name, "success": ok}
    return {"error": f"Unknown action: {action}"}


def check_inventory_tool() -> dict:
    """在庫一覧を返す。"""
    items = db.get_inventory()
    return {"inventory": items, "count": len(items)}


def shopping_list_tool(threshold: float = 1.0) -> dict:
    """
    在庫が閾値以下のアイテムを買い物リストとして返す。

    Args:
        threshold: この数量以下のアイテムをリストアップ
    """
    items = db.get_inventory()
    low = [i for i in items if i["quantity"] <= threshold]
    return {"shopping_list": low, "count": len(low)}


def suggest_recipe_tool(max_items: int = 5) -> dict:
    """
    現在の在庫をもとにGPTへ献立提案を依頼する。

    Args:
        max_items: 提案するレシピ数の上限
    """
    import os
    from openai import OpenAI
    from dotenv import load_dotenv

    load_dotenv()
    items = db.get_inventory()
    if not items:
        return {"error": "在庫が空です。先に食材を登録してください。"}

    item_list = "\n".join(f"- {i['name']}: {i['quantity']}{i['unit']}" for i in items)
    prompt = (
        f"以下の食材が冷蔵庫にあります:\n{item_list}\n\n"
        f"これらを使って作れる献立を{max_items}個提案してください。"
        f"各レシピは「料理名: 使用食材」の形式で返してください。"
    )

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )
    text = response.choices[0].message.content.strip()
    return {"suggestions": text}
