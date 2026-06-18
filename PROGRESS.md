# 開発進捗・引き継ぎメモ (PROGRESS)

複数PC間でセッションを引き継ぐための作業メモ。
**作業を再開する人（または Claude）は、まずこのファイルを読むこと。**

最終更新: 2026-06-19

---

## 🎯 現在の状態

- Day1〜7 + 追加機能（賞味期限・チャットUI・RAG）すべて実装完了。**全テスト 88 件パス**（`python -m pytest -q`）。
- 直近の作業: README 全面改訂（Mermaid アーキテクチャ図 + Playwright 自動撮影スクリーンショット5枚 + デモセクション追加）。
- コミット済み・push 済み。GitHub: https://github.com/chaningdev/fridge-agent

## ✅ 完了済み（Day 別）

| Day | 内容 | 状態 |
|---|---|---|
| 1 | DB設計・API疎通確認 | ✅ コミット済み |
| 2 | parse_receipt_tool | ✅ コミット済み |
| 3 | recognize_dish_tool + router.py | ✅ コミット済み |
| 4 | db.py 在庫ロジック + テスト | ✅ コミット済み |
| 5 | **agent.py**（GPT自律Tool呼び出し）+ router 配線 | ✅ コミット済み |
| 6 | Streamlit UI (app.py) / CLI (demo.py) + エージェントモード | ✅ コミット済み |
| 7 | README.md | ✅ コミット済み |

## 📌 次の作業（TODO）

- [x] 変更分をコミットする（Day5〜7 + 引き継ぎ文書）
- [x] GitHub リモートを作成して push（完了）
- [x] 画像アップロードをサイドバーに統合・レシート/料理を自動判別
- [x] 消費確認画面（テキスト/エージェント）・端数管理・単位拡充
- [ ] 実機で Gemini / OpenAI の動作確認（`.env` にキー設定後 `python check_api.py`）
- [x] 標準賞味期限の自動補完（`src/expiry_master.py` 新規作成）
- [x] 食材名・カテゴリRAG化（`src/normalizer.py` / `src/food_master_data.py` / `build_master.py`）
- [ ] IMPROVEMENTS.md の残り🟡項目（LINE通知・料理写真精度向上 など）

## 🔄 別PCで作業を再開する手順

1. `git pull`（初回は `git clone <repo>`）
2. `pip install -r requirements.txt`
3. `.env` を用意（`.env.example` をコピーしてAPIキーを記入。**`.env` は同期されない**）
4. `python -m pytest -q` で 39 件パスを確認
5. このファイルと CLAUDE.md を読んで状況把握 → 作業開始

## ⚠️ 重要な決定・注意点

- **モデルは `gpt-4o-mini` で統一**。CLAUDE.md の「GPT-5 mini」表記より、動作実績のある実コードを優先した。`Agent(model=...)` で差し替え可能。
- **`.env` と `fridge.db` は `.gitignore` 対象** → 別PCでは `.env` を再作成する必要あり（セキュリティ上これが正しい）。在庫DB `fridge.db` はPC毎に別物になる（必要なら demo.py の `9`（デモデータ投入）で再シード）。
- **Claude のメモリ（`~/.claude/.../memory/`）はPC間で同期されない。** このファイル（PROGRESS.md）が、その代わりの同期用引き継ぎドキュメント。作業後はここを更新してコミットすること。

## 🏗️ アーキテクチャ要点

- `src/agent.py` … GPT が「どのToolを呼ぶか」を自律決定（function-calling）。キー無しは router のルールベースへ自動フォールバック。
- `src/router.py` … ツール → バックエンド（gemini/openai/sqlite）の対応表 + キーワード判定。
- `src/vision.py` … Gemini Vision（レシート / 料理写真）。
- `src/tools.py` … 6つの Tool 本体。
- `src/db.py` … SQLite 在庫ストア。
