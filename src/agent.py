"""Fridge Agent — GPT 主導の自律 Tool 呼び出しオーケストレータ。

アーキテクチャ（LINEヤフー "Agent i" のハイブリッド構成を個人スケールで再現）:
  - 判断・対話（Brain） : OpenAI GPT が「どのToolを呼ぶか」を自律的に決定
  - 画像認識（Vision）  : Gemini（parse_receipt / recognize_dish の内部で使用）
  - 在庫管理           : SQLite
  - ルーティング層      : router.py が「タスク→バックエンド」の対応と、
                         API 不要の決定論的フォールバックを提供

ユーザーは目標を自然文で伝えるだけ。エージェントは目標達成のために
1 つ以上の Tool を（必要なら連続して）自律的に呼び出す。

使い方:
    from src.agent import run_agent
    result = run_agent("在庫を確認して、作れる献立を提案して")
    print(result["reply"])
"""

from __future__ import annotations

import json
import os
from typing import Callable

from dotenv import load_dotenv

from . import tools
from .router import TaskType, backend_for_tool, route

load_dotenv()

# ── ツールレジストリ（name → callable）────────────────────────────────────────
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "parse_receipt_tool":    tools.parse_receipt_tool,
    "recognize_dish_tool":   tools.recognize_dish_tool,
    "update_inventory_tool": tools.update_inventory_tool,
    "check_inventory_tool":  tools.check_inventory_tool,
    "shopping_list_tool":    tools.shopping_list_tool,
    "suggest_recipe_tool":   tools.suggest_recipe_tool,
}

# ── OpenAI function-calling 用のツールスキーマ ────────────────────────────────
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "parse_receipt_tool",
            "description": "レシート画像を読み取り、含まれる食材を在庫に追加する。レシートの画像パスがある時に使う。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "レシート画像のファイルパス"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recognize_dish_tool",
            "description": "料理写真から使用された食材を推定し、在庫から消費する。料理写真の画像パスがある時に使う。",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "料理写真のファイルパス"},
                },
                "required": ["image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_inventory_tool",
            "description": "食材を手動で在庫に追加(add)または消費(consume)する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "食材名"},
                    "quantity": {"type": "number", "description": "数量"},
                    "unit": {"type": "string", "description": "単位（個 / g / ml / 本 など）"},
                    "action": {"type": "string", "enum": ["add", "consume"], "description": "追加(add)か消費(consume)か"},
                },
                "required": ["name", "quantity", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory_tool",
            "description": "現在の在庫一覧を取得する。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shopping_list_tool",
            "description": "在庫が閾値以下の食材を買い物リストとして取得する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number", "description": "この数量以下の食材を対象にする（既定 1.0）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_recipe_tool",
            "description": "現在の在庫をもとに作れる献立を提案する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_items": {"type": "integer", "description": "提案するレシピ数の上限（既定 5）"},
                },
            },
        },
    },
]

SYSTEM_PROMPT = """あなたは冷蔵庫の在庫を管理する AI エージェント「Fridge Agent」です。
ユーザーの目標を達成するために、提供されたツールを自律的に呼び出してください。

方針:
- 在庫の確認・追加・消費、買い物リスト作成、献立提案、画像（レシート／料理写真）の解析ができます。
- 必要なら複数のツールを順番に呼び出して構いません（例: 在庫を確認してから献立を提案する）。
- ユーザーから画像パスが提供された場合は、そのパスをそのまま image_path に渡してください。
- ツールの実行結果を踏まえ、最後はユーザーに分かりやすい日本語で結果を要約してください。
- 数量や単位が不明な場合は常識的な既定値を使ってください。
"""


def _format_result(tool_name: str, result: dict) -> str:
    """ルールベース実行のツール結果を、人間向けの短い日本語に整形する。"""
    if "error" in result:
        return f"⚠️ {result['error']}"

    if tool_name == "check_inventory_tool":
        if result["count"] == 0:
            return "在庫は空です。"
        lines = [f"・{i['name']} {i['quantity']}{i['unit']}" for i in result["inventory"]]
        return f"現在の在庫（{result['count']} 種類）:\n" + "\n".join(lines)

    if tool_name == "shopping_list_tool":
        if result["count"] == 0:
            return "不足している食材はありません。"
        lines = [f"・{i['name']} 残り {i['quantity']}{i['unit']}" for i in result["shopping_list"]]
        return "買い物リスト:\n" + "\n".join(lines)

    if tool_name == "suggest_recipe_tool":
        return result.get("suggestions", "")

    if tool_name == "parse_receipt_tool":
        return f"{result['count']} 件の食材を在庫に追加しました。"

    if tool_name == "recognize_dish_tool":
        msg = f"{len(result['consumed'])} 種類を在庫から消費しました。"
        if result.get("not_found"):
            names = [i["name"] for i in result["not_found"]]
            msg += f"（在庫になかった食材: {names}）"
        return msg

    if tool_name == "update_inventory_tool":
        if result.get("action") == "add":
            return f"{result['name']} {result['quantity']}{result['unit']} を追加しました。"
        return f"{result['name']} を消費しました。" if result.get("success") else "在庫が見つかりませんでした。"

    return json.dumps(result, ensure_ascii=False)


class Agent:
    """GPT の function-calling で自律的にツールを呼び出すエージェント。

    Args:
        client: OpenAI クライアント。None なら遅延生成（テスト時は差し替え可能）。
        model:  使用する OpenAI モデル（既定は tools.py と揃えて gpt-4o-mini）。
    """

    def __init__(self, client=None, model: str = "gpt-4o-mini"):
        self._client = client
        self.model = model

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    def _dispatch(self, name: str, args: dict) -> dict:
        """ツール名と引数から実際のツールを呼び出す。例外は dict に包んで返す。"""
        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            return {"error": f"unknown tool: {name}"}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}
        except Exception as e:  # noqa: BLE001 — ツール失敗をエージェントに伝える
            return {"error": str(e)}

    def run(self, user_input: str, image_path: str | None = None, max_steps: int = 6) -> dict:
        """GPT に目標を渡し、ツールを自律的に呼ばせて結果を返す。

        Returns:
            {"reply": str, "trace": [{"tool", "backend", "args", "result"}, ...]}
        """
        content = user_input
        if image_path:
            content += f"\n\n[添付画像のパス: {image_path}]"

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        trace: list[dict] = []

        for _ in range(max_steps):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
            )
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []

            # アシスタントの発話（とツール呼び出し要求）を履歴へ
            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_entry)

            # ツール呼び出しが無ければ完了
            if not tool_calls:
                return {"reply": msg.content or "", "trace": trace}

            # 要求された全ツールを実行し、結果を履歴へ返す
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch(name, args)
                trace.append({
                    "tool": name,
                    "backend": backend_for_tool(name),
                    "args": args,
                    "result": result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

        return {"reply": "（最大ステップ数に達しました。目標を分割して試してください。）", "trace": trace}

    def run_rule_based(self, user_input: str, image_path: str | None = None, **extra) -> dict:
        """OpenAI を使わず router.py のキーワード判定で 1 ツールを呼ぶフォールバック。

        OPENAI_API_KEY が無い環境やオフラインデモ用。
        """
        r = route(user_input, image_path=image_path, **extra)
        if r.task_type == TaskType.UNKNOWN:
            return {
                "reply": "ご要望を理解できませんでした。"
                         "「在庫を確認」「○○を追加」「買い物リスト」「献立を提案」などをお試しください。",
                "trace": [],
            }
        result = self._dispatch(r.tool_name, r.kwargs)
        return {
            "reply": _format_result(r.tool_name, result),
            "trace": [{
                "tool": r.tool_name,
                "backend": r.model_backend,
                "args": r.kwargs,
                "result": result,
            }],
        }


def run_agent(user_input: str, image_path: str | None = None, use_llm: bool | None = None, **extra) -> dict:
    """エージェント実行の便利関数。

    use_llm が None の場合、OPENAI_API_KEY の有無で自動判定する。
    LLM 実行が失敗した場合はルールベースへフォールバックする。
    """
    if use_llm is None:
        use_llm = bool(os.environ.get("OPENAI_API_KEY"))

    agent = Agent()
    if not use_llm:
        return agent.run_rule_based(user_input, image_path=image_path, **extra)

    try:
        return agent.run(user_input, image_path=image_path)
    except Exception as e:  # noqa: BLE001 — API 失敗時はルールベースで継続
        result = agent.run_rule_based(user_input, image_path=image_path, **extra)
        result["fallback"] = f"LLM 呼び出しに失敗したためルールベースで応答しました: {e}"
        return result


if __name__ == "__main__":
    import sys

    goal = " ".join(sys.argv[1:]) or "在庫を確認して"
    out = run_agent(goal)
    for step in out.get("trace", []):
        print(f"🔧 {step['tool']} [{step['backend']}]")
    if out.get("fallback"):
        print(f"! {out['fallback']}")
    print(out["reply"])
