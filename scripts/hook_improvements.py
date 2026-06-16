"""
Claude Code の PostToolUse フックから呼ばれるスクリプト。
stdin の JSON を読み、編集されたファイルが IMPROVEMENTS.md なら
format_improvements.py を実行する。
"""

import json
import subprocess
import sys
from pathlib import Path

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Edit / Write ツールのファイルパスを取得
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path.endswith("IMPROVEMENTS.md"):
        sys.exit(0)

    script = Path(__file__).parent / "format_improvements.py"
    subprocess.run([sys.executable, str(script)], check=False)


if __name__ == "__main__":
    main()
