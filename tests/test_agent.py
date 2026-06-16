"""Unit tests for agent.py — OpenAI is faked via a stub client."""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import src.agent as agent
import src.db as db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


# ── OpenAI レスポンスを模した軽量スタブ ──────────────────────────────────────
def _msg(content=None, tool_calls=None):
    return types.SimpleNamespace(content=content, tool_calls=tool_calls)


def _resp(message):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _tool_call(call_id, name, arguments):
    return types.SimpleNamespace(
        id=call_id,
        function=types.SimpleNamespace(name=name, arguments=arguments),
    )


class FakeClient:
    """create() を呼ぶたびに、与えた response を順番に返すスタブ。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


# ── run()（GPT 自律呼び出し）─────────────────────────────────────────────────

def test_run_calls_tool_then_replies():
    db.upsert_item("卵", 6, "個")
    responses = [
        _resp(_msg(tool_calls=[_tool_call("c1", "check_inventory_tool", "{}")])),
        _resp(_msg(content="在庫は1種類です")),
    ]
    a = agent.Agent(client=FakeClient(responses))

    out = a.run("在庫を教えて")

    assert out["reply"] == "在庫は1種類です"
    assert out["trace"][0]["tool"] == "check_inventory_tool"
    assert out["trace"][0]["backend"] == "sqlite"
    assert out["trace"][0]["result"]["count"] == 1


def test_run_executes_update_inventory():
    responses = [
        _resp(_msg(tool_calls=[_tool_call(
            "c1", "update_inventory_tool",
            '{"name": "トマト", "quantity": 3, "unit": "個", "action": "add"}',
        )])),
        _resp(_msg(content="トマトを追加しました")),
    ]
    a = agent.Agent(client=FakeClient(responses))

    a.run("トマトを3個追加して")

    inv = {i["name"]: i for i in db.get_inventory()}
    assert inv["トマト"]["quantity"] == 3


def test_run_chains_multiple_tools():
    """在庫確認 → 献立提案 のように複数ツールを順に呼べる。"""
    db.upsert_item("玉ねぎ", 2, "個")
    responses = [
        _resp(_msg(tool_calls=[_tool_call("c1", "check_inventory_tool", "{}")])),
        _resp(_msg(tool_calls=[_tool_call("c2", "shopping_list_tool", '{"threshold": 1.0}')])),
        _resp(_msg(content="完了しました")),
    ]
    a = agent.Agent(client=FakeClient(responses))

    out = a.run("在庫を見て足りないものを教えて")

    assert [t["tool"] for t in out["trace"]] == ["check_inventory_tool", "shopping_list_tool"]
    assert out["reply"] == "完了しました"


def test_run_handles_bad_tool_arguments():
    """壊れた JSON 引数でも例外を投げずに続行する。"""
    responses = [
        _resp(_msg(tool_calls=[_tool_call("c1", "check_inventory_tool", "not-json")])),
        _resp(_msg(content="ok")),
    ]
    a = agent.Agent(client=FakeClient(responses))

    out = a.run("在庫")
    assert out["reply"] == "ok"


def test_run_max_steps_guard():
    """ツール呼び出しが止まらなくても max_steps で打ち切る。"""
    looping = [
        _resp(_msg(tool_calls=[_tool_call(f"c{i}", "check_inventory_tool", "{}")]))
        for i in range(10)
    ]
    a = agent.Agent(client=FakeClient(looping))

    out = a.run("在庫", max_steps=3)
    assert len(out["trace"]) == 3
    assert "最大ステップ" in out["reply"]


# ── run_rule_based()（OpenAI 不要のフォールバック）────────────────────────────

def test_rule_based_check_inventory():
    db.upsert_item("牛乳", 1, "L")
    out = agent.Agent().run_rule_based("在庫を確認して")
    assert out["trace"][0]["tool"] == "check_inventory_tool"
    assert "牛乳" in out["reply"]


def test_rule_based_unknown_returns_guidance():
    out = agent.Agent().run_rule_based("こんにちは")
    assert out["trace"] == []
    assert "理解できませんでした" in out["reply"]


def test_run_agent_auto_selects_rule_based_without_key(monkeypatch):
    """OPENAI_API_KEY が無ければ自動でルールベースになる。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db.upsert_item("豆腐", 1, "丁")
    out = agent.run_agent("在庫を確認して")
    assert out["trace"][0]["tool"] == "check_inventory_tool"
