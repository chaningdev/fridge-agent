"""Task router — maps user intent to the appropriate Tool.

Routing logic:
  image input  →  Gemini (parse_receipt / recognize_dish)
  inventory    →  SQLite direct (update / check / shopping_list)
  recipe/chat  →  OpenAI GPT (suggest_recipe)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class TaskType(Enum):
    PARSE_RECEIPT = auto()
    RECOGNIZE_DISH = auto()
    UPDATE_INVENTORY = auto()
    CHECK_INVENTORY = auto()
    SHOPPING_LIST = auto()
    SUGGEST_RECIPE = auto()
    UNKNOWN = auto()


@dataclass
class RouteResult:
    task_type: TaskType
    tool_name: str
    model_backend: str   # "gemini" | "openai" | "sqlite" | "unknown"
    kwargs: dict


# Tool → backend の対応（マルチベンダー・ルーティングの単一の真実）。
# agent.py はツール実行ごとにここを参照して、どのベンダーが処理したかを記録する。
TOOL_BACKENDS = {
    "parse_receipt_tool":   "gemini",
    "recognize_dish_tool":  "gemini",
    "update_inventory_tool": "sqlite",
    "check_inventory_tool": "sqlite",
    "shopping_list_tool":   "sqlite",
    "suggest_recipe_tool":  "openai",
}


def backend_for_tool(tool_name: str) -> str:
    """ツール名から担当バックエンド（gemini/openai/sqlite）を返す。"""
    return TOOL_BACKENDS.get(tool_name, "unknown")


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Keyword sets for intent detection
_RECEIPT_KW = {"レシート", "receipt", "買い物", "購入", "領収"}
_DISH_KW = {"料理", "dish", "食べた", "食事", "ご飯", "定食", "弁当"}
_CHECK_KW = {"在庫", "inventory", "確認", "一覧", "リスト表示", "何がある"}
_SHOPPING_KW = {"買い物リスト", "shopping list", "買う", "補充", "不足", "切れ"}
_RECIPE_KW = {"レシピ", "献立", "recipe", "何作れる", "提案", "suggest"}
_ADD_KW = {"追加", "add", "入れた", "補充した", "買ってきた"}
_CONSUME_KW = {"消費", "consume", "使った", "使用", "食べた"}


def _is_image_path(text: str) -> bool:
    return Path(text.strip()).suffix.lower() in _IMAGE_EXTS


def _contains(text: str, keywords: set[str]) -> bool:
    return any(kw in text for kw in keywords)


def route(user_input: str, **extra_kwargs) -> RouteResult:
    """
    Determine which tool to call from natural language input.

    Args:
        user_input: ユーザーのテキスト入力
        **extra_kwargs: image_path など追加パラメータ

    Returns:
        RouteResult with tool_name and kwargs ready for dispatch
    """
    text = user_input.strip()
    image_path: str | None = extra_kwargs.get("image_path")

    # --- Image-based tasks ---
    if image_path and _is_image_path(image_path):
        if _contains(text, _RECEIPT_KW) or "receipt" in text.lower():
            return RouteResult(
                task_type=TaskType.PARSE_RECEIPT,
                tool_name="parse_receipt_tool",
                model_backend="gemini",
                kwargs={"image_path": image_path},
            )
        # Default image → dish recognition
        return RouteResult(
            task_type=TaskType.RECOGNIZE_DISH,
            tool_name="recognize_dish_tool",
            model_backend="gemini",
            kwargs={"image_path": image_path},
        )

    # --- Inline image path in text ---
    path_match = re.search(r'[\w/\\:\-]+\.(?:jpg|jpeg|png|webp|gif)', text, re.IGNORECASE)
    if path_match:
        img = path_match.group(0)
        if _contains(text, _RECEIPT_KW):
            return RouteResult(
                task_type=TaskType.PARSE_RECEIPT,
                tool_name="parse_receipt_tool",
                model_backend="gemini",
                kwargs={"image_path": img},
            )
        return RouteResult(
            task_type=TaskType.RECOGNIZE_DISH,
            tool_name="recognize_dish_tool",
            model_backend="gemini",
            kwargs={"image_path": img},
        )

    # --- Inventory management ---
    if _contains(text, _SHOPPING_KW):
        return RouteResult(
            task_type=TaskType.SHOPPING_LIST,
            tool_name="shopping_list_tool",
            model_backend="sqlite",
            kwargs={"threshold": extra_kwargs.get("threshold", 1.0)},
        )

    if _contains(text, _CHECK_KW):
        return RouteResult(
            task_type=TaskType.CHECK_INVENTORY,
            tool_name="check_inventory_tool",
            model_backend="sqlite",
            kwargs={},
        )

    if _contains(text, _ADD_KW):
        return RouteResult(
            task_type=TaskType.UPDATE_INVENTORY,
            tool_name="update_inventory_tool",
            model_backend="sqlite",
            kwargs={
                "name": extra_kwargs.get("name", ""),
                "quantity": extra_kwargs.get("quantity", 1),
                "unit": extra_kwargs.get("unit", "個"),
                "action": "add",
            },
        )

    if _contains(text, _CONSUME_KW):
        return RouteResult(
            task_type=TaskType.UPDATE_INVENTORY,
            tool_name="update_inventory_tool",
            model_backend="sqlite",
            kwargs={
                "name": extra_kwargs.get("name", ""),
                "quantity": extra_kwargs.get("quantity", 1),
                "unit": extra_kwargs.get("unit", "個"),
                "action": "consume",
            },
        )

    # --- Recipe suggestion ---
    if _contains(text, _RECIPE_KW):
        return RouteResult(
            task_type=TaskType.SUGGEST_RECIPE,
            tool_name="suggest_recipe_tool",
            model_backend="openai",
            kwargs={"max_items": extra_kwargs.get("max_items", 5)},
        )

    return RouteResult(
        task_type=TaskType.UNKNOWN,
        tool_name="",
        model_backend="unknown",
        kwargs={},
    )
