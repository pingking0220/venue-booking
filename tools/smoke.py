"""示範模式冒煙測試：開頁、截圖、收集 console 錯誤。用法：python tools/smoke.py [輸出資料夾]"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "out"
OUT.mkdir(parents=True, exist_ok=True)
URL = (ROOT / "index.html").as_uri() + "?demo"

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL); page.wait_for_timeout(800)
    page.evaluate("localStorage.clear()"); page.reload(); page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "day.png"))
    page.click("nav button[data-v=week]"); page.wait_for_timeout(200)
    page.select_option("#week-place", "e150"); page.wait_for_timeout(200)
    page.screenshot(path=str(OUT / "week.png"))
    print("errors:", errors)
    b.close()
