"""Gemini Vision helpers — receipt parsing and dish recognition."""

import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_RECEIPT_PROMPT = """
あなたは食料品レシートを読み取るアシスタントです。
添付の画像はスーパーや食料品店のレシートです。

## 抽出ルール
- 食品・飲料・調味料のみ対象（消耗品・日用品・ポイント・割引行は除外）
- 数量が不明な場合は 1 にする
- 単位が不明な場合は "個" にする
- 名前は日本語で返す

## 【最重要】食材名の正規化ルール
レシートの商品名には産地・ブランド・規格・調理状態などが混じっているが、
**在庫管理に使う汎用名（何の食材か）のみを返すこと。**

除去すべき要素:
- 産地・地域名: 淡路、四国、北海道、国産、青森、九州 など
- ブランド・銘柄名: プライベートブランド名、メーカー名
- 規格・サイズ: 大玉、Lサイズ、特大、業務用
- 形状・調理状態（食材の種類が変わらない場合）: カット済み、千切り、スライス

## 正規化の例（Few-shot）
| レシートの商品名 | → nameに入れる値 |
|---|---|
| 淡路玉ねぎ | 玉ねぎ |
| 四国玉ねぎ | 玉ねぎ |
| 北海道じゃがいも | じゃがいも |
| 国産豚ロース薄切り | 豚ロース |
| 青森産りんご | りんご |
| PB 特濃牛乳 | 牛乳 |
| MサイズLL卵 10個入 | 卵 |
| カット済みほうれん草 | ほうれん草 |
| 九州産鶏もも肉 300g | 鶏もも肉 |

## 数量・単位のルール
- "卵 10個入" → quantity: 10, unit: "個"
- "牛乳 1L" → quantity: 1, unit: "L"
- 重量・容量が書いてあれば読み取る（g / ml / L / 本 / 枚 / 丁 / 袋 など）

必ず以下のJSON形式 **のみ** を返してください（説明文不要）:
[
  {"name": "食材名", "quantity": 数値, "unit": "単位"},
  ...
]
""".strip()

_DISH_PROMPT = """
あなたは料理写真から使用食材を推定するアシスタントです。
添付の画像は完成した料理の写真です。

この料理を作るために使われたと思われる主な食材を推定してください。
- 主材料・副材料を含める（野菜・肉・魚・豆腐・卵など）
- 調味料（醤油・塩・砂糖・みりん・酒など）は省略する
- 数量は一人前の目安を記載
- g / ml / 個 / 枚 / 本 / 切れ / 合 など適切な単位を使う
- 判断できない食材は "適量" を 0.5 として扱う

必ず以下のJSON形式 **のみ** を返してください（説明文不要）:
[
  {"name": "食材名", "quantity": 数値, "unit": "単位"},
  ...
]
""".strip()


def _get_client():
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _load_image_part(image_path: str | Path):
    from google.genai import types

    path = Path(image_path)
    mime = _MIME_MAP.get(path.suffix.lower(), "image/jpeg")
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


def _call_gemini(contents, max_retries: int = 4) -> str:
    client = _get_client()
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
            )
            return response.text
        except Exception as e:
            err = str(e)
            is_retryable = "429" in err or "503" in err or "UNAVAILABLE" in err
            if is_retryable and attempt < max_retries - 1:
                wait = 2 ** attempt   # 1s → 2s → 4s → 8s
                print(f"[vision] {err[:60]}… retry {attempt+1}/{max_retries-1} in {wait}s")
                time.sleep(wait)
            else:
                raise


def _parse_json_response(text: str) -> list[dict]:
    """Extract JSON array from model response with multiple fallback strategies."""
    original = text
    text = text.strip()

    # 1. コードフェンスを除去
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # 2. [...] ブロックを抽出（前後に余分なテキストがある場合）
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)

    # 3. JSON パース（失敗したら末尾の不完全なエントリを除去して再試行）
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 末尾の不完全エントリ除去: 最後の完結した } までを残す
        truncated = re.sub(r",?\s*\{[^}]*$", "", text).rstrip(",").strip()
        if not truncated.endswith("]"):
            truncated += "]"
        try:
            data = json.loads(truncated)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini のレスポンスを JSON に変換できませんでした: {e}\n---\n{original[:300]}") from e

    if not isinstance(data, list):
        raise ValueError(f"期待するJSON配列ではありません: {type(data)}")

    # 4. 各アイテムのキーを正規化
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("食材名") or "不明").strip()
        if name in ("不明", ""):
            continue
        try:
            qty = float(item.get("quantity") or item.get("数量") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        unit = str(item.get("unit") or item.get("単位") or "個").strip()
        result.append({"name": name, "quantity": qty, "unit": unit})
    return result


def parse_receipt(image_path: str | Path) -> list[dict]:
    """Return list of {name, quantity, unit} parsed from a receipt image."""
    img = _load_image_part(image_path)
    raw = _call_gemini([img, _RECEIPT_PROMPT])
    return _parse_json_response(raw)


def recognize_dish(image_path: str | Path) -> list[dict]:
    """Return estimated ingredients {name, quantity, unit} from a dish photo."""
    img = _load_image_part(image_path)
    raw = _call_gemini([img, _DISH_PROMPT])
    return _parse_json_response(raw)


_DISH_NAME_PROMPT_TMPL = """
あなたは料理の食材を把握するアシスタントです。

「{dish_name}」を1人前作るときに必要な主な食材を答えてください。
- 調味料（醤油・塩・砂糖・みりん・酒・油など）は除外する
- 主材料・副材料のみを含める
- 数量は1人前の目安
- 単位は g / ml / 個 / 枚 / 本 / 丁 / 袋 など適切なものを使う

必ず以下のJSON形式 **のみ** を返してください（説明文不要）:
[
  {{"name": "食材名", "quantity": 数値, "unit": "単位"}},
  ...
]
""".strip()


def ingredients_from_dish_name(dish_name: str) -> list[dict]:
    """Return typical ingredients for a named dish (text-only, no image)."""
    prompt = _DISH_NAME_PROMPT_TMPL.format(dish_name=dish_name.strip())
    raw = _call_gemini([prompt])
    return _parse_json_response(raw)
