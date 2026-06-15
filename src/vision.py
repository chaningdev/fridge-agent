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

以下のルールに従って食材・食品のみを抽出してください:
- 食品・飲料・調味料のみ対象（消耗品・日用品は除外）
- 数量が不明な場合は 1 にする
- 単位が不明な場合は "個" にする
- 名前は日本語で返す

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


def _call_gemini(contents, max_retries: int = 3) -> str:
    client = _get_client()
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
            )
            return response.text
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[vision] rate-limited, retrying in {wait}s…")
                time.sleep(wait)
            else:
                raise


def _parse_json_response(text: str) -> list[dict]:
    """Extract JSON array from model response, stripping markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Fallback: extract first [...] block if outer text is present
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    data = json.loads(text)
    # Normalize: ensure required keys exist
    result = []
    for item in data:
        result.append({
            "name": str(item.get("name", "不明")),
            "quantity": float(item.get("quantity", 1)),
            "unit": str(item.get("unit", "個")),
        })
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
