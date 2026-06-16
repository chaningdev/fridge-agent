# 開発進捗・引き継ぎメモ (PROGRESS)

複数PC間でセッションを引き継ぐための作業メモ。
**作業を再開する人（または Claude）は、まずこのファイルを読むこと。**

最終更新: 2026-06-16

---

## 🎯 現在の状態

- Day1〜7 を一通り実装完了。**全テスト 39 件パス**（`python -m pytest -q`）。
- 直近の作業: `src/agent.py`（GPT 自律 Tool 呼び出し）を新規実装し、router / demo / app に配線。README 作成。
- ⚠️ **未コミットの変更あり**（下記「次の作業」参照）。

## ✅ 完了済み（Day 別）

| Day | 内容 | 状態 |
|---|---|---|
| 1 | DB設計・API疎通確認 | ✅ コミット済み |
| 2 | parse_receipt_tool | ✅ コミット済み |
| 3 | recognize_dish_tool + router.py | ✅ コミット済み |
| 4 | db.py 在庫ロジック + テスト | ✅ コミット済み |
| 5 | **agent.py**（GPT自律Tool呼び出し）+ router 配線 | ✅ 実装済み・**未コミット** |
| 6 | Streamlit UI (app.py) / CLI (demo.py) + エージェントモード | ✅ 実装済み（UIへの配線分が未コミット） |
| 7 | README.md | ✅ 作成済み・**未コミット** |

## 📌 次の作業（TODO）

- [ ] 変更分をコミットする（未コミット: `src/agent.py`, `tests/test_agent.py`, `README.md`, `PROGRESS.md` 新規 + `src/router.py` `demo.py` `app.py` `requirements.txt` 変更）
- [ ] GitHub リモートを作成して push（Day7「GitHub公開」）
- [ ] 実機で Gemini / OpenAI の動作確認（`.env` にキー設定後 `python check_api.py`）
- [ ] （任意）レシート・料理写真のサンプル画像を用意して画像認識をデモ

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
