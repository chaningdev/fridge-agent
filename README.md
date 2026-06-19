# Fridge Agent — 冷蔵庫在庫管理 AI エージェント

レシートと料理写真から冷蔵庫の在庫を自動管理する AI エージェント。
ユーザーが目標を自然文で伝えるだけで、エージェントが複数の Tool を自律的に呼び出して処理します。

> 本プロジェクトは AIエージェントのアーキテクチャ（OpenAI と Google のハイブリッド構成 + 領域別ルーティング層）を個人スケールで再現することを設計目標としています。

---

## デモ

### AI エージェントが在庫確認 → 献立提案を自律実行

![エージェントが check_inventory_tool と suggest_recipe_tool を自律的に呼び出して献立を提案する画面](docs/screenshots/04_agent_chat.png)

> GPT が「どの Tool を呼ぶか」を自律決定。`check_inventory_tool [sqlite]` → `suggest_recipe_tool [openai]` の順に呼び出し、在庫食材から献立を提案。

---

### 在庫一覧（賞味期限アラート付き）

![在庫一覧ページ。メトリクス・賞味期限警告・カテゴリフィルタ・色分けされた期限インジケーター](docs/screenshots/01_inventory.png)

---

### 買い物リスト / 追加フォーム / 操作履歴

| 買い物リスト | 食材を追加 | 操作履歴 |
|---|---|---|
| ![買い物リスト](docs/screenshots/02_shopping.png) | ![追加・消費フォーム](docs/screenshots/03_add_consume.png) | ![操作履歴テーブル](docs/screenshots/05_history.png) |

---

## 主な機能

| 機能 | 説明 | バックエンド |
|---|---|---|
| **レシート読み取り** | レシート画像 → 食材リスト → 在庫自動追加 | Gemini 2.5 Flash |
| **料理写真から消費** | 料理写真 → 使用食材を推定 → 在庫から消費 | Gemini 2.5 Flash |
| **自然文エージェント** | "在庫確認して献立提案して" → Tool を自律呼び出し | GPT-4o-mini + function-calling |
| **賞味期限管理** | 食材ごとの標準賞味期限を自動補完・アラート表示 | SQLite |
| **食材名 RAG 正規化** | "淡路たまねぎ" → "玉ねぎ" にベクトル検索で正規化 | OpenAI embedding + SQLite |
| **買い物リスト** | 在庫が閾値以下の食材を自動抽出 | SQLite |

---

## アーキテクチャ

```mermaid
graph TD
    U[ユーザー<br>自然文 / 画像]:::user

    subgraph Agent Layer
        A[agent.py<br>GPT function-calling<br>どのToolを呼ぶか自律決定]:::agent
        R[router.py<br>Task → Backend の対応表<br>APIキーなし時のフォールバック]:::router
    end

    subgraph Tool Layer
        T1[parse_receipt_tool]:::tool
        T2[recognize_dish_tool]:::tool
        T3[check_inventory_tool]:::tool
        T4[update_inventory_tool]:::tool
        T5[suggest_recipe_tool]:::tool
        T6[shopping_list_tool]:::tool
    end

    subgraph Backend Layer
        G[Gemini 2.5 Flash<br>画像認識]:::gemini
        O[GPT-4o-mini<br>判断・提案]:::openai
        DB[(SQLite<br>在庫DB)]:::db
    end

    subgraph RAG Layer
        N[normalizer.py<br>食材名正規化]:::rag
        FM[(food_master<br>62食材マスタ)]:::db
        FE[(food_embeddings<br>ベクトルDB)]:::db
    end

    U --> A
    A --> R --> T1 & T2 & T3 & T4 & T5 & T6
    T1 & T2 --> G
    T5 --> O
    T3 & T4 & T6 --> DB
    T1 --> N --> FM & FE

    classDef user fill:#4A90D9,stroke:none,color:#fff
    classDef agent fill:#7B68EE,stroke:none,color:#fff
    classDef router fill:#9B8EC4,stroke:none,color:#fff
    classDef tool fill:#5BA85A,stroke:none,color:#fff
    classDef gemini fill:#EA4335,stroke:none,color:#fff
    classDef openai fill:#10A37F,stroke:none,color:#fff
    classDef db fill:#F5A623,stroke:none,color:#fff
    classDef rag fill:#E67E22,stroke:none,color:#fff
```

### 設計のポイント

| レイヤー | 役割 | 設計の意図 |
|---|---|---|
| **Agent** | GPT が function-calling で Tool を自律選択 | LLM が "脳"、Tool が "手足" |
| **Router** | Task → Backend の単一対応表 | モデル差し替え時の変更箇所を1ファイルに集約 |
| **RAG Normalizer** | ベクトル検索で食材名を正規化 | ファジーマッチ（API不要）→ 埋め込み検索の2段構え |

---

## RAG 正規化の仕組み

```
[Index（オフライン）]   build_master.py --embed
  食材マスタ 62件 → text-embedding-3-small → SQLite (food_embeddings)

[Retrieve（実行時）]   normalize("淡路たまねぎ")
  Step1: ファジーマッチ (difflib)  → スコア >= 0.72 で採用（API不要・高速）
  Step2: 埋め込みベクトル検索     → cos類似度 >= 0.80 で採用（意味的類似）

[Augment]             parse_receipt() の Gemini プロンプトに正規名リストを注入
  → Gemini が出力段階で正規名に揃えやすくなる
```

---

## セットアップ

### 1. 依存をインストール

```bash
pip install -r requirements.txt
```

### 2. API キーを設定

```bash
cp .env.example .env
# .env を編集して GEMINI_API_KEY と OPENAI_API_KEY を記入
```

> `OPENAI_API_KEY` が未設定でも、エージェントはキーワードベースの**ルールベースモード**で動作します。

### 3.（任意）食材マスタと埋め込みを構築

```bash
python build_master.py          # マスタDB更新
python build_master.py --embed  # 埋め込み生成（OPENAI_API_KEY 必要）
```

### 4. アプリを起動

```bash
streamlit run app.py
```

---

## テスト

API 呼び出しはすべてモック済み。API キー不要で実行できます。

```bash
python -m pytest -q   # 88 件
```

| テストファイル | 対象 |
|---|---|
| `tests/test_db.py` | 在庫の追加・消費・賞味期限ロジック |
| `tests/test_tools.py` | 各 Tool（Vision はモック） |
| `tests/test_vision.py` | JSON パーサ / router 判定 |
| `tests/test_agent.py` | エージェントの自律 Tool 呼び出し / フォールバック |
| `tests/test_expiry.py` | 標準賞味期限マスタ |
| `tests/test_normalizer.py` | RAG 正規化（ファジーマッチ・alias 解決） |

---

## ディレクトリ構成

```
Agent/
├── app.py                  # Streamlit UI（チャット形式）
├── demo.py                 # 対話型 CLI デモ
├── build_master.py         # 食材マスタ & 埋め込み構築スクリプト
├── check_api.py            # API 疎通確認
├── src/
│   ├── agent.py            # GPT 主導の自律 Tool 呼び出し
│   ├── router.py           # Task → Backend ルーティング層
│   ├── vision.py           # Gemini Vision（レシート / 料理写真）
│   ├── tools.py            # 6 つの Tool 定義
│   ├── db.py               # SQLite 在庫ストア
│   ├── normalizer.py       # RAG 食材名ノーマライザー
│   ├── food_master_data.py # 食材マスタデータ（62 食材）
│   └── expiry_master.py    # 標準賞味期限マスタ
└── tests/                  # 88 件（API モック済み）
```

---

## 技術スタック

| 分類 | 技術 |
|---|---|
| Language | Python 3.11 |
| 画像認識 | Google Gemini API（Gemini 2.5 Flash） |
| 判断・対話 | OpenAI API（gpt-4o-mini / function-calling） |
| 食材名正規化 | OpenAI Embeddings（text-embedding-3-small）+ difflib |
| DB | SQLite |
| UI | Streamlit |
| Test | pytest（88 件） |

---

---

## 開発の歩み — 実際に使いながら見つけた問題と改善

一度に完成させたのではなく、実際に使いながら気づいた問題を [IMPROVEMENTS.md](IMPROVEMENTS.md) に記録し、優先度をつけて1つずつ解決していきました。以下はその記録です。

### AI 精度の改善

| 気づいた問題 | 解決策 | 技術的アプローチ |
|---|---|---|
| レシートに「淡路玉ねぎ」「九州産鶏もも肉」と書いてあり、在庫DBに産地込みの名前が登録されてしまう | Gemini プロンプトに正規化ルールと Few-shot 例を追加し、汎用名に変換させる | Prompt Engineering |
| Few-shot だけでは珍しい産地名・カタカナ表記・英語名の揺れをカバーしきれない | 食材マスタ 62 件をベクトル化して SQLite に保存。**ファジーマッチ → 埋め込み検索**の 2 段 RAG を実装し、Gemini プロンプトにも正規名リストを注入 | RAG（Index / Retrieve / Augment）|
| Gemini のレスポンスがたまに JSON 以外の文字を含みパースエラーになる | コードフェンス除去 → 正規表現抽出 → 末尾の不完全エントリ切り捨て再試行、という複数フォールバック戦略を実装 | エラーハンドリング |

> **RAG 導入の経緯：** 最初はプロンプトで解決しようとしたが、レシートの商品名の多様性（産地・ブランド・規格の組み合わせ）には Few-shot では限界があった。「LLM の入力を外部知識で補強する」RAG パターンを適用することで、プロンプト肥大化なしに精度を向上させた。

---

### UX の改善

| 気づいた問題 | 解決策 |
|---|---|
| 料理写真を読み込んだとき、確認なしに在庫が消費されて間違いが修正できない | 認識結果を確認画面として表示し、数量を編集してから在庫に反映するフローに変更 |
| 「カレーを食べた」とテキスト入力しても、確認なしに在庫が消える | エージェント経由の消費にも同様の確認フローを追加（dry_run モードで推定食材を先に提示） |
| 画像アップロードはサイドバー、テキスト入力はメイン画面と操作が分断されていた | `st.chat_input(accept_file=True)` でテキストと画像を同一入力欄に統合（LINE 風 UI） |
| ダークテーマで一部のテキストが背景と同化して読めない | CSS 変数を使いテーマに追従するスタイルに修正 |

---

### データ管理の改善

| 気づいた問題 | 解決策 |
|---|---|
| レシートに賞味期限が書いていないため、いつ使い切ればいいか分からない | 食材ごとの標準保存日数マスタ（`expiry_master.py`）を作成し、登録時に自動補完。在庫一覧に期限アラートを表示 |
| 「玉ねぎ半分使った」が登録できず、0 個か 1 個しか記録できない | 数量フィールドを小数点対応に変更（0.5 個・100g など自由に記録可能） |
| お菓子やカップ麺も「食材」として混ざり、献立提案に不自然な結果が出る | 「完成品」カテゴリを追加し、献立提案・消費推定ロジックではこのカテゴリを除外 |

---

## 今後の展望

### タスク特化ファインチューニングへの移行

現在は Gemini・GPT の汎用モデルをプロンプト設計と RAG で補いながら使用しています。  
個人・家族スケールでは現状精度で十分ですが、精度の上限はプロンプトに依存しており、以下の改善余地があります。

| タスク | 現状 | 理想 |
|---|---|---|
| レシート → 食材名正規化 | Few-shot + RAG で補正 | 日本語レシートデータで特化学習した Vision モデル |
| 料理写真 → 使用食材推定 | 汎用 Gemini の画像認識 | 和食・家庭料理データセットで特化学習 |
| 自然文 → Tool 選択 | GPT function-calling | 冷蔵庫管理ドメインの対話データでファインチューニング |

**`router.py` を抽象化層として設計した理由のひとつ**は、将来ファインチューニングしたモデルへ切り替える際に、`TOOL_BACKENDS` 辞書を変えるだけで対応できるようにするためです。

---

## 設計判断

技術的な判断の記録は [DECISIONS.md](DECISIONS.md) を参照してください。
マルチベンダー構成の理由・フォールバック設計・RAGパターンの適用・ファインチューニングの展望について記録しています。
