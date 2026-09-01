#!/usr/bin/env python3
"""验证排名榜国家列在窄屏下不竖排。"""
import os
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tmp", "verify_rankings.png")
OUT_NARROW = os.path.join(ROOT, "tmp", "verify_rankings_narrow.png")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

URL = "http://localhost:8765/#rankings"

def dump_info(page):
    return page.evaluate("""() => {
      const b = document.getElementById('rankBody');
      const first = b.querySelector('tr');
      const cell = first ? first.querySelector('.c-country') : null;
      return {
        firstRowText: first ? first.innerText : null,
        countryCellText: cell ? cell.innerText : null,
        countryCellRect: cell ? {width: cell.getBoundingClientRect().width, height: cell.getBoundingClientRect().height} : null
      };
    }""")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)

    # 1) 390px 窄屏：验证国家列不竖排
    ctx1 = browser.new_context(viewport={"width": 390, "height": 1200})
    page1 = ctx1.new_page()
    page1.goto(URL, wait_until="networkidle", timeout=60000)
    page1.wait_for_selector("#rankBody tr", timeout=30000)
    print("390px:", dump_info(page1))
    page1.screenshot(path=OUT_NARROW, full_page=True)
    ctx1.close()

    # 2) 820px 宽度：展示完整表格
    ctx2 = browser.new_context(viewport={"width": 820, "height": 1200})
    page2 = ctx2.new_page()
    page2.goto(URL, wait_until="networkidle", timeout=60000)
    page2.wait_for_selector("#rankBody tr", timeout=30000)
    print("820px:", dump_info(page2))
    page2.evaluate("document.querySelector('.rank-table').scrollIntoView({block:'start'})")
    page2.wait_for_timeout(500)
    page2.screenshot(path=OUT, full_page=False)
    ctx2.close()

    browser.close()

print(f"截图已保存: {OUT}, {OUT_NARROW}")
