"""Fridge Agent — Streamlit UI"""

import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

# Streamlit Cloud: Secrets を os.environ に転写（dotenv の代替）
try:
    for _k, _v in st.secrets.items():
        if _k not in os.environ:
            os.environ[_k] = str(_v)
except Exception:
    pass  # ローカル環境では st.secrets が空なのでスキップ

sys.path.insert(0, str(Path(__file__).parent))

import importlib
import src.db as db
import src.tools as tools
import src.agent as agent
importlib.reload(db)   # Streamlit の sys.modules キャッシュを無効化
importlib.reload(tools)

db.init_db()

# デモ用初期データ（在庫が空のときだけ投入）
def _seed_demo() -> None:
    from datetime import date, timedelta
    if db.get_inventory():
        return
    today = date.today()
    demo_items = [
        ("卵",       6,   "個",  "卵",    None),
        ("牛乳",     1,   "L",   "乳製品", (today + timedelta(days=2)).isoformat()),
        ("鶏もも肉", 300, "g",   "肉・魚", (today + timedelta(days=1)).isoformat()),
        ("玉ねぎ",   3,   "個",  "野菜",   None),
        ("じゃがいも", 4, "個",  "野菜",   None),
        ("にんじん",  2,  "本",  "野菜",   (today + timedelta(days=10)).isoformat()),
        ("豆腐",      1,  "丁",  "その他", (today + timedelta(days=4)).isoformat()),
        ("ご飯",      2,  "合",  "穀物",   None),
        ("ポテトチップス", 1, "袋", "完成品", None),
        ("カップ麺",  2,  "個",  "完成品", None),
    ]
    for name, qty, unit, cat, exp in demo_items:
        db.upsert_item(name, qty, unit, source="demo", category=cat, expires_at=exp)

_seed_demo()

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
    from datetime import date as _date

    result = tools.check_inventory_tool()
    items = result["inventory"]
    expiring = db.get_expiring_items(days=3)

    # ── メトリクス ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("食材の種類", result["count"])
    low = [i for i in items if i["quantity"] <= 1]
    col2.metric("残量少ない食材", len(low), delta_color="inverse")
    col3.metric("期限切れ間近", len(expiring), delta_color="inverse")

    # ── 期限切れアラート ────────────────────────────────────────────────────────
    if expiring:
        today = _date.today().isoformat()
        expired  = [i for i in expiring if i["expires_at"] < today]
        soon     = [i for i in expiring if i["expires_at"] >= today]
        if expired:
            names = "、".join(i["name"] for i in expired)
            st.error(f"🚨 期限切れ: **{names}**")
        if soon:
            names = "、".join(f"{i['name']}（{i['expires_at']}）" for i in soon)
            st.warning(f"⚠️ 期限切れ間近（3日以内）: **{names}**")

    st.divider()

    # ── 在庫一覧 ───────────────────────────────────────────────────────────────
    def _expiry_badge(exp: str | None) -> str:
        if not exp:
            return ""
        today = _date.today().isoformat()
        days_left = (_date.fromisoformat(exp) - _date.today()).days
        if days_left < 0:
            return f"🔴 期限切れ（{exp}）"
        if days_left <= 3:
            return f"🟠 あと{days_left}日（{exp}）"
        if days_left <= 7:
            return f"🟡 あと{days_left}日（{exp}）"
        return f"🟢 {exp}"

    if not items:
        st.info("在庫がありません。食材を追加してください。")
    else:
        # ── カテゴリフィルタ ───────────────────────────────────────────────────
        from src.db import CATEGORIES, READY_FOOD_CATEGORY
        all_cats = sorted({i.get("category") or "" for i in items})
        cat_options = ["すべて"] + [c if c else "（未分類）" for c in all_cats]
        selected_cat = st.selectbox("カテゴリで絞り込み", cat_options, index=0)

        if selected_cat != "すべて":
            filter_cat = "" if selected_cat == "（未分類）" else selected_cat
            display_items = [i for i in items if (i.get("category") or "") == filter_cat]
        else:
            display_items = items

        # 完成品の件数バッジ
        ready_count = sum(1 for i in items if i.get("category") == READY_FOOD_CATEGORY)
        if ready_count:
            st.info(f"🍫 完成品（お菓子・インスタント等）: {ready_count} 種類 — 献立提案・買い物リストからは除外されます")

        st.subheader("在庫一覧")
        # ヘッダー行
        h1, h2, h3, h4, h5 = st.columns([3, 1.5, 1.5, 2, 1])
        for col, label in zip([h1,h2,h3,h4,h5], ["食材名","数量","カテゴリ","賞味期限","残量"]):
            col.markdown(f"**{label}**")
        st.divider()

        for item in display_items:
            c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 2, 1])
            cat = item.get("category") or ""
            cat_label = f"🍫 {cat}" if cat == READY_FOOD_CATEGORY else (cat or "—")
            c1.write(item["name"])
            c2.write(f"{item['quantity']} {item['unit']}")
            c3.write(cat_label)
            c4.write(_expiry_badge(item.get("expires_at")))
            qty_icon = "🔴" if item["quantity"] <= 1 else "🟡" if item["quantity"] <= 3 else "🟢"
            c5.write(qty_icon)

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
            col3, col4 = st.columns(2)
            from src.db import CATEGORIES
            category = col3.selectbox("カテゴリ", CATEGORIES)
            expires = col4.date_input("賞味期限（任意）", value=None)
            submitted = st.form_submit_button("追加する", type="primary")

        if submitted:
            if not name.strip():
                st.error("食材名を入力してください")
            else:
                expires_str = expires.isoformat() if expires else None
                tools.update_inventory_tool(
                    name.strip(), qty, unit, action="add",
                    category=category, expires_at=expires_str,
                )
                st.success(f"✅ **{name}** {qty}{unit} を追加しました")
                st.rerun()

    with tab_consume:
        sub_tab_manual, sub_tab_dish = st.tabs(["手動で消費", "料理名で消費"])

        with sub_tab_manual:
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
                        st.error("❌ 在庫が見つかりません")

        with sub_tab_dish:
            st.caption("料理名を入力すると、その料理の標準食材を在庫から自動消費します")
            dish_input = st.text_input("料理名", placeholder="例: カレー、肉じゃが、親子丼を食べた")
            if st.button("🍽️ 消費する", type="primary", key="consume_dish"):
                if not dish_input.strip():
                    st.error("料理名を入力してください")
                else:
                    with st.spinner("Gemini で食材を推定中..."):
                        try:
                            result = tools.consume_by_dish_name_tool(dish_input)
                            st.success(f"**{result['dish']}** の食材を消費しました")
                            if result["consumed"]:
                                st.write("消費した食材:")
                                for item in result["consumed"]:
                                    st.write(f"  ✅ {item['name']} {item['quantity']}{item['unit']}")
                            if result["not_found"]:
                                st.warning("在庫になかった食材（スキップ）:")
                                for item in result["not_found"]:
                                    st.write(f"  ⚠️ {item['name']}")
                        except Exception as e:
                            err = str(e)
                            if "503" in err or "UNAVAILABLE" in err:
                                st.error("⚠️ Gemini が混雑しています。しばらくしてから再試行してください。")
                            else:
                                st.error(f"❌ {err}")

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
    import src.vision as vision

    mode = st.radio("モード", ["レシート → 食材追加", "料理写真 → 食材消費"], horizontal=True)

    # session_state keys for dish confirmation flow
    _SS_INGREDIENTS = "dish_ingredients_pending"
    _SS_IMAGE_MODE  = "dish_image_mode"

    # Reset pending state when mode switches
    if st.session_state.get(_SS_IMAGE_MODE) != mode:
        st.session_state.pop(_SS_INGREDIENTS, None)
        st.session_state[_SS_IMAGE_MODE] = mode

    uploaded = st.file_uploader(
        "画像をアップロード",
        type=["jpg", "jpeg", "png", "webp"],
        help="レシートまたは料理の写真をアップロードしてください",
    )

    if uploaded:
        st.image(uploaded, width=300)

        # ── レシートモード ─────────────────────────────────────────────────────
        if "レシート" in mode:
            if st.button("🔍 Gemini で解析する", type="primary"):
                with st.spinner("Gemini に送信中（混雑時は自動リトライします）..."):
                    try:
                        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as f:
                            f.write(uploaded.read())
                            tmp_path = f.name
                        result = tools.parse_receipt_tool(tmp_path)
                        if "error" in result:
                            st.error(result["error"])
                        else:
                            st.success(f"✅ {result['count']} 件の食材を在庫に追加しました")
                            for item in result["added"]:
                                st.write(f"  - **{item['name']}** {item['quantity']}{item['unit']}")
                    except Exception as e:
                        err = str(e)
                        if "503" in err or "UNAVAILABLE" in err:
                            st.error("⚠️ Gemini サーバーが混雑しています。しばらく待ってから再試行してください。")
                        elif "429" in err:
                            st.error("⚠️ APIのレート制限に達しました。少し時間をおいてから再試行してください。")
                        else:
                            st.error(f"❌ エラーが発生しました: {err}")

        # ── 料理写真モード（2ステップ確認フロー） ──────────────────────────────
        else:
            # Step 1: Gemini で解析
            if _SS_INGREDIENTS not in st.session_state:
                if st.button("🔍 Gemini で解析する", type="primary"):
                    with st.spinner("Gemini に送信中（混雑時は自動リトライします）..."):
                        try:
                            with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as f:
                                f.write(uploaded.read())
                                tmp_path = f.name
                            items = vision.recognize_dish(tmp_path)
                            if not items:
                                st.warning("食材を認識できませんでした。別の写真を試してください。")
                            else:
                                st.session_state[_SS_INGREDIENTS] = items
                                st.rerun()
                        except Exception as e:
                            err = str(e)
                            if "503" in err or "UNAVAILABLE" in err:
                                st.error("⚠️ Gemini サーバーが混雑しています。しばらく待ってから再試行してください。")
                            elif "429" in err:
                                st.error("⚠️ APIのレート制限に達しました。少し時間をおいてから再試行してください。")
                            else:
                                st.error(f"❌ エラーが発生しました: {err}")

            # Step 2: 編集・確認フォーム
            else:
                pending = st.session_state[_SS_INGREDIENTS]
                st.subheader("🍽️ 認識した食材（修正してから確認してください）")
                st.caption("チェックを外すと消費しません。数量も変更できます。")

                edited = []
                for i, item in enumerate(pending):
                    col_chk, col_name, col_qty, col_unit = st.columns([0.5, 3, 1.5, 1.5])
                    checked = col_chk.checkbox("", value=True, key=f"dish_chk_{i}")
                    name = col_name.text_input("食材名", value=item["name"], key=f"dish_name_{i}", label_visibility="collapsed")
                    qty  = col_qty.number_input("数量", value=float(item["quantity"]), min_value=0.0, step=0.5, key=f"dish_qty_{i}", label_visibility="collapsed")
                    unit = col_unit.text_input("単位", value=item["unit"], key=f"dish_unit_{i}", label_visibility="collapsed")
                    if checked and name.strip():
                        edited.append({"name": name.strip(), "quantity": qty, "unit": unit})

                st.divider()
                col_ok, col_cancel = st.columns([1, 1])
                if col_ok.button("✅ 確認して在庫から消費", type="primary"):
                    consumed, not_found = [], []
                    for item in edited:
                        ok = db.consume_item(item["name"], item["quantity"], source="dish")
                        (consumed if ok else not_found).append(item)
                    del st.session_state[_SS_INGREDIENTS]
                    if consumed:
                        st.success(f"✅ {len(consumed)} 種類を消費しました")
                        for item in consumed:
                            st.write(f"  - **{item['name']}** {item['quantity']}{item['unit']}")
                    if not_found:
                        st.warning("在庫になかった食材（スキップ）:")
                        for item in not_found:
                            st.write(f"  ⚠️ {item['name']}")
                    st.rerun()
                if col_cancel.button("❌ キャンセル"):
                    del st.session_state[_SS_INGREDIENTS]
                    st.rerun()
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
