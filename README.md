# 🧊 Fridge Agent — 冷蔵庫在庫管理AIエージェント

レシートと料理写真から冷蔵庫の在庫を自動管理する AI エージェント。
ユーザーは **目標を自然文で伝えるだけ**で、エージェントが複数の Tool を自律的に呼び出して処理します。

> 本プロジェクトは LINEヤフー「Agent i」のアーキテクチャ（OpenAI と Google のハイブリッド構成 + 領域別ルーティング層）を、個人スケールで再現することを設計目標としています。

---

## ✨ 特徴

- 📸 **レシート画像 → 食材を自動で在庫に追加**（Gemini Vision）
- 🍽️ **料理写真 → 使った食材を推定して在庫から消費**（Gemini Vision）
- 🤖 **自然文の目標 → GPT が自律的に Tool を呼び出し**（OpenAI function-calling）
- 🛒 在庫確認・買い物リスト生成・献立提案
- 🌐 マルチベンダー・ルーティング層（画像→Gemini / 判断・対話→GPT / 在庫→SQLite）
- 🇯🇵🇬🇧 日本語・英語の両対応

---

## 🏗️ アーキテクチャ

```
ユーザーの目標（自然文）
        │
        ▼
   ┌─────────┐      判断・対話（Brain）
   │ agent.py │ ───────────────────────►  OpenAI GPT
   └─────────┘   どのToolを呼ぶかを自律決定
        │
        ▼
   ┌──────────┐    タスク → バックエンドの対応 / API不要のフォールバック
   │ router.py │
   └──────────┘
        │
        ▼
   ┌──────────────────────── tools.py ────────────────────────┐
   │ parse_receipt / recognize_dish  →  Gemini Vision (vision.py) │
   │ update / check / shopping_list  →  SQLite        (db.py)     │
   │ suggest_recipe                  →  OpenAI GPT               │
   └────────────────────────────────────────────────────────────┘
```

`agent.py` が GPT 主導で「どの Tool を呼ぶか」を決め、`router.py` が「どのベンダーが処理するか」を司る二層構成です。

---

## 🛠️ Tool 一覧

| Tool 名 | 役割 | バックエンド |
|---|---|---|
| `parse_receipt_tool` | レシート画像 → 食材リスト → 在庫追加 | Gemini Vision |
| `recognize_dish_tool` | 料理画像 → 使用食材推定 → 在庫消費 | Gemini Vision |
| `update_inventory_tool` | 在庫を手動で追加 / 消費 | SQLite |
| `check_inventory_tool` | 在庫一覧を返す | SQLite |
| `shopping_list_tool` | 在庫が閾値以下の食材を抽出 | SQLite |
| `suggest_recipe_tool` | 在庫から献立提案 | OpenAI GPT |

---

## 🚀 セットアップ

### 1. 依存をインストール

```powershell
pip install -r requirements.txt
```

### 2. API キーを設定

`.env.example` をコピーして `.env` を作成し、キーを記入します。

```powershell
Copy-Item .env.example .env
```

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

> `OPENAI_API_KEY` が無くても、エージェントはキーワードベースの**ルールベースモード**で動作します（画像認識・献立提案は各 API キーが必要）。

### 3. API 疎通確認（任意）

```powershell
python check_api.py
```

---

## 💻 使い方

### Streamlit UI

```powershell
streamlit run app.py
```

サイドバーから「🤖 エージェント」「📦 在庫」「📸 画像読み込み」「🍽️ 献立提案」などを切り替えられます。

### 対話型 CLI デモ

```powershell
python demo.py
```

メニュー `a`（AIエージェントに目標を伝える）で自然文の指示を試せます。
`9`（デモデータ投入）で在庫を仮投入してから試すのがおすすめです。

### コードから直接

```python
from src.agent import run_agent

result = run_agent("在庫を確認して、作れる献立を提案して")
print(result["reply"])
for step in result["trace"]:
    print(step["tool"], "→", step["backend"])
```

---

## 🧪 テスト

Gemini / OpenAI の呼び出しはすべてモックしているため、API キー無しで実行できます。

```powershell
python -m pytest -q
```

| テストファイル | 対象 |
|---|---|
| `tests/test_db.py` | 在庫の追加・消費・履歴 |
| `tests/test_tools.py` | 各 Tool（Vision はモック） |
| `tests/test_vision.py` | JSON パーサ / router 判定 |
| `tests/test_agent.py` | エージェントの自律 Tool 呼び出し / フォールバック |

---

## 📂 ディレクトリ構成

```
Agent/
├── app.py              # Streamlit UI
├── demo.py             # 対話型 CLI デモ
├── check_api.py        # API 疎通確認
├── requirements.txt
├── .env.example
├── src/
│   ├── agent.py        # GPT 主導の自律 Tool 呼び出し
│   ├── router.py       # タスク → バックエンドのルーティング層
│   ├── vision.py       # Gemini Vision（レシート / 料理写真）
│   ├── tools.py        # 6 つの Tool 定義
│   └── db.py           # SQLite 在庫ストア
└── tests/
    ├── test_db.py
    ├── test_tools.py
    ├── test_vision.py
    └── test_agent.py
```

---

## 📋 技術スタック

- Python 3.10+
- 画像認識: Google Gemini API（Gemini 2.5 Flash）
- 判断・対話: OpenAI API（gpt-4o-mini）
- DB: SQLite
- UI: Streamlit
