"""Fridge Agent — Streamlit UI"""

import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src import agent, db, tools

db.init_db()

# ── ページ設定 ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fridge Agent",
    page_icon="🧊",
    layout="wide",
)

st.title("🧊 Fridge Agent")
st.caption("レシート・料理写真から冷蔵庫在庫を自動管理するAIエージェント")

# ── サイドバー ────────────────────────────────────────────────────────────────
page = st.sidebar.radio(
    "メニュー",
    ["🤖 エージェント", "📦 在庫", "➕ 追加・消費", "🛒 買い物リスト", "📸 画像読み込み", "🍽️ 献立提案", "📋 履歴"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# AIエージェントページ — 自然文の目標から自律的にToolを呼び出す
# ═══════════════════════════════════════════════════════════════════════════════
if page == "🤖 エージェント":
    st.subheader("AIエージェントに目標を伝える")
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    if has_key:
        st.caption("GPT が目標を解釈し、必要なToolを自律的に呼び出します。")
    else:
        st.caption("⚠️ OPENAI_API_KEY 未設定のため、キーワードによるルールベースで動作します。")

    examples = "例: 「在庫を確認して」「トマトを3個追加して」「足りないものを教えて」「献立を提案して」"
    goal = st.text_input("目標", placeholder=examples)

    if st.button("🚀 実行", type="primary") and goal.strip():
        with st.spinner("エージェントが処理中..."):
            result = agent.run_agent(goal.strip())

        if result.get("fallback"):
            st.warning(result["fallback"])

        if result.get("trace"):
            with st.expander("🔧 呼び出したTool（マルチベンダー・ルーティング）", expanded=True):
                for step in result["trace"]:
                    st.write(f"- `{step['tool']}` → **{step['backend']}**")

        st.divider()
        st.markdown(result["reply"])

# ═══════════════════════════════════════════════════════════════════════════════
# 在庫ページ
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📦 在庫":
    result = tools.check_inventory_tool()
    items = result["inventory"]

    col1, col2 = st.columns(2)
    col1.metric("食材の種類", result["count"])
    low = [i for i in items if i["quantity"] <= 1]
    col2.metric("残量少ない食材", len(low), delta_color="inverse")

    st.divider()

    if not items:
        st.info("在庫がありません。食材を追加してください。")
    else:
        # 残量ゲージ付きテーブル
        st.subheader("在庫一覧")
        for item in items:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(item["name"])
            c2.write(f"{item['quantity']} {item['unit']}")
            color = "🔴" if item["quantity"] <= 1 else "🟡" if item["quantity"] <= 3 else "🟢"
            c3.write(color)

    if st.button("🔄 更新"):
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# 追加・消費ページ
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "➕ 追加・消費":
    tab_add, tab_consume = st.tabs(["食材を追加", "食材を消費"])

    with tab_add:
        with st.form("add_form"):
            name = st.text_input("食材名", placeholder="例: 卵")
            col1, col2 = st.columns(2)
            qty  = col1.number_input("数量", min_value=0.1, value=1.0, step=0.5)
            unit = col2.selectbox("単位", ["個", "g", "ml", "本", "枚", "丁", "袋", "L", "合", "切れ"])
            submitted = st.form_submit_button("追加する", type="primary")

        if submitted:
            if not name.strip():
                st.error("食材名を入力してください")
            else:
                tools.update_inventory_tool(name.strip(), qty, unit, action="add")
                st.success(f"✅ **{name}** {qty}{unit} を追加しました")
                st.rerun()

    with tab_consume:
        items = db.get_inventory()
        if not items:
            st.info("在庫がありません")
        else:
            with st.form("consume_form"):
                names = [i["name"] for i in items]
                selected = st.selectbox("食材", names)
                qty = st.number_input("消費量", min_value=0.1, value=1.0, step=0.5)
                submitted = st.form_submit_button("消費する", type="primary")

            if submitted:
                result = tools.update_inventory_tool(selected, qty, action="consume")
                if result.get("success"):
                    st.success(f"✅ **{selected}** {qty} を消費しました")
                    st.rerun()
                else:
                    st.error(f"❌ 在庫が見つかりません")

# ═══════════════════════════════════════════════════════════════════════════════
# 買い物リスト
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🛒 買い物リスト":
    threshold = st.slider("残量の閾値（これ以下を表示）", 0.5, 5.0, 1.0, 0.5)
    result = tools.shopping_list_tool(threshold=threshold)

    if not result["shopping_list"]:
        st.success("不足している食材はありません 🎉")
    else:
        st.warning(f"**{result['count']} 種類**の食材が不足しています")
        for item in result["shopping_list"]:
            st.write(f"- **{item['name']}**　残り {item['quantity']}{item['unit']}")

# ═══════════════════════════════════════════════════════════════════════════════
# 画像読み込み
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📸 画像読み込み":
    mode = st.radio("モード", ["レシート → 食材追加", "料理写真 → 食材消費"], horizontal=True)

    uploaded = st.file_uploader(
        "画像をアップロード",
        type=["jpg", "jpeg", "png", "webp"],
        help="レシートまたは料理の写真をアップロードしてください",
    )

    if uploaded:
        st.image(uploaded, width=300)

        if st.button("🔍 Gemini で解析する", type="primary"):
            with st.spinner("Gemini に送信中..."):
                with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as f:
                    f.write(uploaded.read())
                    tmp_path = f.name

                if "レシート" in mode:
                    result = tools.parse_receipt_tool(tmp_path)
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(f"✅ {result['count']} 件の食材を在庫に追加しました")
                        for item in result["added"]:
                            st.write(f"  - **{item['name']}** {item['quantity']}{item['unit']}")
                else:
                    result = tools.recognize_dish_tool(tmp_path)
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(f"✅ {len(result['consumed'])} 種類を消費しました")
                        for item in result["consumed"]:
                            st.write(f"  - **{item['name']}** {item['quantity']}{item['unit']}")
                        if result["not_found"]:
                            st.warning(f"在庫になかった食材: {[i['name'] for i in result['not_found']]}")
    else:
        st.info("画像をアップロードすると Gemini が自動で食材を認識します")

# ═══════════════════════════════════════════════════════════════════════════════
# 献立提案
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🍽️ 献立提案":
    items = db.get_inventory()
    if not items:
        st.warning("在庫がありません。先に食材を登録してください。")
    else:
        st.subheader("現在の在庫")
        cols = st.columns(4)
        for i, item in enumerate(items):
            cols[i % 4].write(f"**{item['name']}** {item['quantity']}{item['unit']}")

        st.divider()
        max_items = st.slider("提案するレシピ数", 1, 10, 5)

        if st.button("🤖 GPT に献立を提案してもらう", type="primary"):
            with st.spinner("OpenAI に送信中..."):
                result = tools.suggest_recipe_tool(max_items=max_items)
            if "error" in result:
                st.error(result["error"])
            else:
                st.subheader("献立の提案")
                st.write(result["suggestions"])

# ═══════════════════════════════════════════════════════════════════════════════
# 履歴
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📋 履歴":
    history = db.get_history(limit=30)
    if not history:
        st.info("操作履歴がありません")
    else:
        import pandas as pd
        df = pd.DataFrame(history)
        df = df[["created_at", "action", "item_name", "quantity", "unit", "source"]]
        df.columns = ["日時", "操作", "食材", "数量", "単位", "ソース"]
        df["日時"] = df["日時"].str[:19]
        df["操作"] = df["操作"].map({"add": "➕ 追加", "consume": "➖ 消費"})
        st.dataframe(df, use_container_width=True, hide_index=True)
