# Fridge Agent — 冷蔵庫在庫管理AIエージェント

> 📌 **作業を再開するときは、まず [PROGRESS.md](PROGRESS.md) を読むこと。**
> 現在の進捗・次の作業・PC間引き継ぎ情報がまとまっている（複数PCで開発するため）。

## 1. プロジェクトの目的

レシートと料理写真から冷蔵庫の在庫を自動管理するAIエージェント。
ユーザーは「目標」を伝えるだけで、エージェントが複数のToolを自律的に呼び出して処理する。

このプロジェクトは LINEヤフー「Agent i」のアーキテクチャ（OpenAIとGoogleのハイブリッド構成 + 領域別ルーティング層）を、個人スケールで再現することを設計目標とする。

## 2. 技術スタック

- 言語: Python 3.10+
- 画像認識: Google Gemini API（Gemini 2.5 Flash）
- 判断・対話: OpenAI API（GPT-5 mini）
- DB: SQLite
- UI: Streamlit
- 対応言語: 日本語・英語の両対応
- 環境変数: python-dotenv で .env からAPIキーを読み込む

## 3. ディレクトリ構成

Agent/
├── CLAUDE.md
├── README.md
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── app.py
├── src/
│   ├── __init__.py
│   ├── agent.py
│   ├── router.py
│   ├── vision.py
│   ├── db.py
│   └── tools.py
└── tests/
    └── test_db.py

## 4. Toolの一覧

| Tool名 | 役割 | モデル |
|---|---|---|
| parse_receipt_tool | レシート画像→食材リスト | Gemini Vision |
| recognize_dish_tool | 料理画像→使用食材推定 | Gemini Vision |
| update_inventory_tool | 在庫を追加/消費 | SQLite |
| check_inventory_tool | 在庫一覧を返す | SQLite |
| suggest_recipe_tool | 在庫から献立提案 | GPT |
| shopping_list_tool | 買い物リスト生成 | SQLite |

## 5. マルチベンダー・ルーティング設計

タスクの特性に応じてモデルを使い分けるルーティング層を自作する。
- 画像認識 → Gemini
- 判断・対話・提案 → GPT
これはAgent iのアーキテクチャ（OpenAI+Googleハイブリッド）と同じ設計思想。

## 6. 実装スケジュール

Day1: 環境構築・DB設計・API疎通確認
Day2: parse_receipt_tool（レシート→食材）
Day3: recognize_dish_tool（料理→食材推定）
Day4: db.py 在庫管理ロジック + テスト
Day5: agent.py + router.py（Tool自律呼び出し）
Day6: Streamlit UI・デモ動作確認
Day7: README作成・GitHub公開

## 7. コーディング方針

- APIキーは必ず .env から読む。ハードコード禁止
- 画像認識の結果はJSON形式で受け取る
- APIエラー（429）は指数バックオフでリトライ
- 各Toolは単体でテストできる設計にする
