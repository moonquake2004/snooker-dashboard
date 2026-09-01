#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证排名页冠军数显示：无 JS 报错、podium 与表格均渲染、窄屏无溢出。"""
import os, sys
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = "file://" + os.path.join(BASE, "index.html")
SHOT = os.path.join(BASE, "scripts", "_verify_titles.png")

errors = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(HTML)
    pg.wait_for_selector("#rankings", state="attached")

    # 切到排名页
    pg.evaluate("document.querySelector('.nav-link[data-tab=rankings]').click()")
    pg.wait_for_selector("#rankBody tr", state="visible", timeout=8000)
    pg.wait_for_timeout(300)

    # podium 冠军数
    pod = pg.query_selector_all("#rankPodium .podium .pod-titles .tt-cell")
    pod_none = pg.query_selector_all("#rankPodium .podium .pod-titles .tt-none")
    # 表格冠军数（含 0 冠的 tt-none）
    tbl_cells = pg.query_selector_all("#rankBody .c-titles .tt-cell")
    tbl_none = pg.query_selector_all("#rankBody .c-titles .tt-none")
    # 表头是否新增“冠军”列
    ths = [t.inner_text() for t in pg.query_selector_all(".rank-table thead th")]

    # 取前 3 行文本核对赵心童等
    rows = [r.inner_text().replace("\n", " | ") for r in pg.query_selector_all("#rankBody tr")[:4]]

    pg.screenshot(path=SHOT, full_page=False)

    # 窄屏检查横向溢出
    pg.set_viewport_size({"width": 390, "height": 844})
    pg.wait_for_timeout(300)
    overflow = pg.evaluate("document.querySelector('.table-scroll').scrollWidth - document.querySelector('.table-scroll').clientWidth")
    pg.screenshot(path=SHOT.replace(".png", "_mobile.png"), full_page=False)

    browser.close()

print("JS 错误:", errors if errors else "无")
print("表头:", ths)
print("podium 冠军徽章数:", len(pod), "| podium 0冠占位:", len(pod_none))
print("表格冠军徽章数:", len(tbl_cells), "| 表格0冠占位:", len(tbl_none))
print("窄屏 table-scroll 横向溢出(px):", overflow)
print("前4行:")
for r in rows: print("  ", r)
