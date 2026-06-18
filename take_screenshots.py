"""ポートフォリオ用スクリーンショット自動撮影スクリプト（Playwright）。"""

import asyncio
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8501"
OUT_DIR  = Path(__file__).parent / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
VIEWPORT = {"width": 1280, "height": 800}


async def wait_st(page, extra: float = 1.5) -> None:
    await page.wait_for_load_state("networkidle", timeout=15000)
    await asyncio.sleep(extra)


async def nav(page, label: str) -> None:
    await page.locator("label", has_text=label).first.click()
    await wait_st(page)


async def take_screenshots() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport=VIEWPORT)

        print("Streamlit に接続中...")
        await page.goto(BASE_URL, wait_until="networkidle")
        await wait_st(page, 2.0)

        # ── 1. 在庫一覧 ────────────────────────────────────────────────────
        print("撮影: 在庫一覧")
        await nav(page, "在庫")
        await page.screenshot(path=str(OUT_DIR / "01_inventory.png"))
        print("  -> 01_inventory.png")

        # ── 2. 買い物リスト ────────────────────────────────────────────────
        print("撮影: 買い物リスト")
        await nav(page, "買い物リスト")
        # しきい値を 2 に上げてより多く表示
        slider = page.locator("[data-testid='stSlider'] input[type='range']").first
        try:
            await slider.fill("2")
            await wait_st(page)
        except Exception:
            pass
        await page.screenshot(path=str(OUT_DIR / "02_shopping.png"))
        print("  -> 02_shopping.png")

        # ── 3. 追加フォーム ────────────────────────────────────────────────
        print("撮影: 追加・消費")
        await nav(page, "追加・消費")
        await page.screenshot(path=str(OUT_DIR / "03_add_consume.png"))
        print("  -> 03_add_consume.png")

        # ── 4. エージェント（チャット応答を含む） ──────────────────────────
        print("撮影: エージェント (チャット応答待ち...)")
        await nav(page, "エージェント")
        await wait_st(page)

        # チャット入力欄にメッセージを送信
        chat_input = page.locator("textarea").first
        await chat_input.click()
        await chat_input.fill("在庫を確認して、作れる料理を1つ提案して")
        await chat_input.press("Enter")

        # GPT の応答を待つ（最大 60 秒）
        print("  GPT 応答待ち (最大60秒)...")
        try:
            await page.wait_for_selector(
                "[data-testid='stChatMessage']",
                timeout=60000,
            )
            await wait_st(page, 2.0)
        except Exception:
            print("  タイムアウト: 空の状態で撮影")
            await asyncio.sleep(2)

        await page.screenshot(path=str(OUT_DIR / "04_agent_chat.png"))
        print("  -> 04_agent_chat.png")

        # ── 5. 履歴 ────────────────────────────────────────────────────────
        print("撮影: 履歴")
        await nav(page, "履歴")
        await page.screenshot(path=str(OUT_DIR / "05_history.png"))
        print("  -> 05_history.png")

        await browser.close()

    saved = sorted(OUT_DIR.glob("0?.png") )
    for f in saved:
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")
    print(f"\n完了: {len(saved)} 枚")


if __name__ == "__main__":
    asyncio.run(take_screenshots())
