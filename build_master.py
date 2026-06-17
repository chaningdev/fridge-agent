#!/usr/bin/env python
"""食材マスタDBの構築・確認スクリプト。

Usage:
    python build_master.py          # マスタDBを更新（埋め込みは生成しない）
    python build_master.py --embed  # マスタ更新 + 埋め込み生成（OPENAI_API_KEY 必須）
    python build_master.py --check  # 現在の件数を確認するだけ
"""

import sys
from dotenv import load_dotenv

load_dotenv()

from src import db
from src.normalizer import build_embeddings


def check_status() -> None:
    master = db.get_food_master()
    embeddings = db.get_food_embeddings()
    print(f"食材マスタ: {len(master)} 件")
    print(f"埋め込み  : {len(embeddings)} 件")
    if master and embeddings:
        not_embedded = [m["canonical"] for m in master
                        if m["canonical"] not in {e["canonical"] for e in embeddings}]
        if not_embedded:
            print(f"埋め込み未生成: {', '.join(not_embedded[:10])}")
        else:
            print("全件の埋め込みが生成済みです。")


def main() -> None:
    db.init_db()
    args = sys.argv[1:]

    if "--check" in args:
        check_status()
        return

    # マスタDB更新
    count = db.build_food_master()
    print(f"食材マスタを更新しました（{count} 件）")

    if "--embed" in args:
        print("埋め込みを生成します…")
        built = build_embeddings()
        print(f"完了: {built} 件の埋め込みを生成しました。")
    else:
        print("ヒント: 埋め込みを生成するには --embed を付けてください（OPENAI_API_KEY 必須）")

    check_status()


if __name__ == "__main__":
    main()
