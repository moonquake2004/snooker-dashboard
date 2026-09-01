#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 wst.tv 各赛事信息页抓取奖金信息（总奖金、冠军奖金，以及完整的奖金分配表）。

wst.tv 的 tournaments 接口不含 prize money 字段，但每个赛事的 informationPage
正文里通常写有 "Total prize money will be £X, with the winner to receive £Y"，
部分页面还带有完整的分配表（Winner / Runner-up / Semi-final ...）。

输出：data/raw/prize_pages.json —— 保存每个赛事抓到的原文片段，供人工/脚本解析。
"""

import html
import json
import os
import re
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wst.tv/",
}

# 奖金分配表的行标签（中英对照）
TIER_ZH = {
    "winner": "冠军",
    "runner-up": "亚军",
    "runner up": "亚军",
    "losing semi finalist": "四强",
    "semi-finalist": "四强",
    "semi-final": "四强",
    "semi final": "四强",
    "quarter-finalist": "八强",
    "quarter-final": "八强",
    "quarter final": "八强",
    "last 16": "16强",
    "last 32": "32强",
    "last 64": "64强",
    "last 128": "128强",
    "highest break": "单杆最高分",
    # 总额只在 "total prize ..." 语境下才算，避免误配裸 total
    "total prize fund": "总奖金",
    "total prize money": "总奖金",
    "total prize": "总奖金",
}

# 窗口内金额与标签的最大字符距离，超过则视为误配
MAX_PAIR_DIST = 90

MONEY_RE = re.compile(r"£\s?([0-9][0-9,]*)")

# WST 页面偶见的千分位排版错误，例如英锦赛写成 "£312,0500"（实为 £312,500）
BAD_THOUSANDS = re.compile(r",\d{4,}")


def normalize_money(raw):
    """
    修正 WST 页面上的千分位笔误。

    例：英锦赛页面写作 "£312,0500"，而总额为 £1,500,000、亚军 £125,000，
    正确值应为 £312,500 —— 即第二组多敲了一个前导 0。
    """
    parts = raw.split(",")
    if not all(p.isdigit() for p in parts):
        return None
    if len(parts) == 1:
        return int(parts[0])

    fixed = [parts[0]]
    for p in parts[1:]:
        if len(p) == 3:
            fixed.append(p)
        elif len(p) > 3 and p.startswith("0"):
            # 多敲了前导 0，截掉使其回到 3 位
            fixed.append(p[len(p) - 3:])
        else:
            fixed.append(p)
    try:
        return int("".join(fixed))
    except ValueError:
        return None


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(seg):
    txt = re.sub(r"<[^>]+>", "\n", seg)
    txt = html.unescape(txt).replace("\\n", "\n")
    return txt


def extract_text_lines(raw_html):
    """去标签后的纯文本行。"""
    txt = strip_tags(raw_html)
    txt = re.sub(r"[ \t]+", " ", txt)
    return [l.strip() for l in txt.split("\n") if l.strip()]


def extract_prize_snippets(lines, limit=6):
    """抽出与奖金相关的原文片段，便于人工核对。"""
    hits = []
    for i, line in enumerate(lines):
        if "prize" in line.lower() or "\u00a3" in line:
            hits.append(" ".join(lines[max(0, i - 1):i + 2])[:600])
    return hits[:limit]


def find_total(lines):
    """
    单独解析总奖金。WST 有两种表述：
      A. "Total prize money will be £850,000, with the winner to receive £177,000"
      B. 奖金表末行 "Total £1,500,000"
    两者与通用窗口匹配的阈值/关键字都不兼容，因此单独处理。
    """
    best = None
    for line in lines:
        if "£" not in line:
            continue
        low = line.lower()
        m = re.search(r"total\s+prize[^£]{0,80}£\s?([0-9][0-9,]*)", low)
        if not m:
            m = re.match(r"\s*total\s*:?\s*£\s?([0-9][0-9,]*)", low)
        if not m:
            continue
        v = normalize_money(m.group(1))
        if v is not None and (best is None or v > best):
            best = v
    return best


def parse_breakdown(lines, window=2):
    """
    从正文中解析逐档奖金。

    部分站点（如冠中冠官网）用表格排版，金额与档位标签被拆到不同单元格，
    去标签后落在不同行。因此对每个含金额的行取前后若干行组成窗口，
    在窗口内按「金额与标签距离最近」配对。
    """
    out = {}
    total = find_total(lines)
    if total is not None:
        out["\u603b\u5956\u91d1"] = total
    for i, line in enumerate(lines):
        if "\u00a3" not in line:
            continue
        lo, hi = max(0, i - window), min(len(lines), i + window + 1)
        win_lines = lines[lo:hi]
        low = " ".join(win_lines).lower()

        moneys, off = [], 0
        for l in win_lines:
            for mm in MONEY_RE.finditer(l):
                v = normalize_money(mm.group(1))
                if v is not None:
                    moneys.append((off + mm.start(), v))
            off += len(l) + 1
        if not moneys:
            continue

        for key, zh in TIER_ZH.items():
            km = re.search(re.escape(key), low)
            if not km:
                continue
            pos, val = min(moneys, key=lambda t: abs(t[0] - km.start()))
            if abs(pos - km.start()) > MAX_PAIR_DIST:
                continue  # 标签与金额离得太远，不可信
            total = out.get("\u603b\u5956\u91d1")
            if zh != "\u603b\u5956\u91d1" and total and val > total:
                continue  # 单档奖金不可能超过总额，视为误配
            if zh not in out or val > out[zh]:
                out[zh] = val
    return out


def main():
    tour_path = os.path.join(RAW_DIR, "tournaments.json")
    with open(tour_path, encoding="utf-8") as fh:
        tours = json.load(fh)

    targets = []
    for t in tours:
        a = t["attributes"]
        sd = a.get("startDate") or ""
        if not ("2026-06-01" <= sd <= "2027-06-01"):
            continue
        if re.search(r"qualifiers?$", a["name"], re.I):
            continue
        page = (a.get("informationPage") or "").strip()
        if not page:
            continue
        if page.startswith("http"):
            url = page
        else:
            # informationPage 有的写成 "/ukchampionship"，有的漏了斜杠
            url = "https://www.wst.tv/" + page.lstrip("/")
        targets.append({"id": t["id"], "name": a["name"], "url": url})

    # 冠军联赛各阶段共用同一信息页，按 URL 去重
    seen_urls = {}
    uniq = []
    for tg in targets:
        if tg["url"] in seen_urls:
            seen_urls[tg["url"]].append(tg["id"])
            continue
        seen_urls[tg["url"]] = [tg["id"]]
        uniq.append(tg)

    print(f"待抓取赛事页：{len(uniq)}（去重后，覆盖 {len(targets)} 个赛事条目）")
    results = {}
    for i, tg in enumerate(uniq, 1):
        print(f"  [{i}/{len(uniq)}] {tg['name']}")
        try:
            raw = fetch(tg["url"])
        except Exception as exc:  # noqa: BLE001
            print(f"      ✗ 抓取失败: {exc}")
            continue
        lines = extract_text_lines(raw)
        snippets = extract_prize_snippets(lines)
        bd = parse_breakdown(lines)
        # 冠军必须小于总额，否则视为解析失败
        if bd.get("冠军") and bd.get("总奖金") and bd["冠军"] >= bd["总奖金"]:
            print(f"      ⚠ 冠军({bd['冠军']}) ≥ 总额({bd['总奖金']})，丢弃")
            bd.pop("冠军", None)
        payload = {
            "name": tg["name"],
            "url": tg["url"],
            "breakdown": bd,
            "snippets": snippets,
        }
        for tid in seen_urls[tg["url"]]:
            results[tid] = payload
        def gbp(v):
            return f"£{v:,}" if isinstance(v, int) else "?"

        print("      总/冠: " + (f"{gbp(bd.get('总奖金'))} / {gbp(bd.get('冠军'))}"
                                if bd else "（未解析到）"))
        time.sleep(0.4)

    out_path = os.path.join(RAW_DIR, "prize_pages.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    print(f"\n✓ 已保存 {out_path}（{len(results)} 个赛事）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
