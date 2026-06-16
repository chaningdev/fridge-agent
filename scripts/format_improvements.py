"""
IMPROVEMENTS.md を読んで、自由記述の行を
  - [ ] [カテゴリ] 優先度  内容
の形式に自動変換して書き戻す。

フックから呼ばれる: python scripts/format_improvements.py
単体でも動く: python scripts/format_improvements.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TARGET = ROOT / "IMPROVEMENTS.md"

HEADER = """\
# 改善メモ

気づいたことを自由に書いてOK。フォーマットは自動で整える。
実装したら `[ ]` → `[x]` に変えるだけ。
詳しい設計判断は → [DECISIONS.md](DECISIONS.md)

---
"""

CATEGORIES = ["画像", "DB", "UI", "機能", "バグ", "アーキテクチャ"]
PRIORITIES = ["🔴", "🟡", "⚪"]

_CAT_PAT = r"(画像|DB|UI|機能|バグ|アーキテクチャ)"

# フォーマット済み行のパターン: - [ ] [カテゴリ] 優先度  内容
_FORMATTED = re.compile(
    rf"^- \[[ x]\] \[{_CAT_PAT}\] (🔴|🟡|⚪)\s+.+"
)
# カテゴリだけ指定されている行: - [ ] [カテゴリ] 内容
_PARTIAL_CAT = re.compile(rf"^- \[[ x]\] \[{_CAT_PAT}\]\s*(.*)")
# 優先度だけ指定されている行: - [ ] 🔴 内容
_PARTIAL_PRI = re.compile(r"^- \[[ x]\] (🔴|🟡|⚪)\s+(.*)")
# チェックだけの行: - [ ] 内容 or - [x] 内容
_BARE = re.compile(r"^- \[( |x)\] (.+)")


def _guess_category(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["画像", "レシート", "写真", "認識", "gemini", "vision", "精度", "ocr"]):
        return "画像"
    if any(k in t for k in ["db", "データ", "テーブル", "sqlite", "在庫", "履歴", "スキーマ"]):
        return "DB"
    if any(k in t for k in ["ui", "画面", "表示", "ボタン", "streamlit", "デザイン", "色", "フォント",
                             "ダークテーマ", "テーマ", "見えない", "レイアウト", "文字", "アイコン"]):
        return "UI"
    if any(k in t for k in ["バグ", "エラー", "不具合", "クラッシュ", "失敗", "bug", "error"]):
        return "バグ"
    return "機能"


def _guess_priority(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["🔴", "高", "重要", "urgent", "必須", "すぐ"]):
        return "🔴"
    if any(k in t for k in ["⚪", "低", "いつか", "余裕"]):
        return "⚪"
    return "🟡"


def _format_line(line: str) -> str:
    """1行を正規フォーマットに変換する。既にフォーマット済みならそのまま返す。"""
    stripped = line.rstrip()

    # 空行・ヘッダー・区切り・コードブロック → そのまま
    if not stripped or stripped.startswith("#") or stripped.startswith("---") or stripped.startswith("```"):
        return stripped

    # すでに正規フォーマット
    if _FORMATTED.match(stripped):
        return stripped

    # - [ ] [カテゴリ] 内容（優先度なし）
    m = _PARTIAL_CAT.match(stripped)
    if m:
        cat, rest = m.group(1), m.group(2).strip()
        pri = _guess_priority(rest)
        check = "x" if "[x]" in stripped else " "
        return f"- [{check}] [{cat}] {pri}  {rest}" if rest else stripped

    # - [ ] 🔴 内容（カテゴリなし）
    m = _PARTIAL_PRI.match(stripped)
    if m:
        pri, rest = m.group(1), m.group(2).strip()
        cat = _guess_category(rest)
        check = "x" if "[x]" in stripped else " "
        return f"- [{check}] [{cat}] {pri}  {rest}"

    # - [ ] 内容（カテゴリも優先度もなし）
    m = _BARE.match(stripped)
    if m:
        check, rest = m.group(1), m.group(2).strip()
        cat = _guess_category(rest)
        pri = _guess_priority(rest)
        return f"- [{check}] [{cat}] {pri}  {rest}"

    # それ以外（普通のテキスト・リンク行など）→ そのまま
    return stripped


def format_file(path: Path = TARGET) -> bool:
    """ファイルを読み込んでフォーマット済み内容で書き戻す。変更があれば True を返す。"""
    if not path.exists():
        return False

    original = path.read_text(encoding="utf-8")

    # ヘッダー以降の行だけ変換（ヘッダーは固定）
    lines = original.splitlines()
    formatted_lines = [_format_line(l) for l in lines]
    result = "\n".join(formatted_lines) + "\n"

    if result == original:
        return False

    path.write_text(result, encoding="utf-8")
    print(f"[format_improvements] {path.name} を整形しました")
    return True


if __name__ == "__main__":
    changed = format_file()
    sys.exit(0)
