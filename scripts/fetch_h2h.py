#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取球员两两「生涯交手记录 H2H」—— 数据源 CueTracker。

CueTracker 结构（已核实）：
  交手页：https://cuetracker.net/head-to-head/{slugA}/{slugB}
  该页「Past Matches」逐场列出两人所有职业交手，每行含：
    player_1_name / player_2_name（链接里带 slug）、player_1_score / player_2_score
  赢家 = 局分高者。由此可推导 A 对 B 的生涯胜负与逐场记录。

抓取策略：
  - 取世界排名前 N 名球员（来自 data/dashboard.json 的 World Rankings），解析各自 CueTracker slug
  - 对这 N 人两两组合（C(n,2) 对），各抓一次 H2H 页 → 完整覆盖前 N 名内部的所有交手
  - 限流：并发 2、间隔 0.8s（与 fetch_titles.py 一致，CueTracker 密集请求会返 500）
  - 落盘缓存 data/raw/h2h_raw/，重跑只补缺失；产出 data/h2h.json + data/h2h.js

注意：本脚本是「全量刷新」的一部分（refresh.sh），不进轻量刷新 refresh_live.sh，
      符合用户「只更新进行中赛事」的偏好——H2H 属生涯统计，无需每日追更。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://cuetracker.net"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(RAW, "h2h_raw")
os.makedirs(CACHE, exist_ok=True)
OUT_JSON = os.path.join(ROOT, "data", "h2h.json")
OUT_JS = os.path.join(ROOT, "data", "h2h.js")

WORKERS = 2
DELAY = 0.8
TOP = 24
HERE_DASH = os.path.join(ROOT, "data", "dashboard.json")
SLUGS_CACHE = os.path.join(RAW, "titles_cache", "_slugs.json")

_lock = __import__("threading").Lock()
_last = [0.0]
_stats = {"ok": 0, "err": 0, "skip": 0}


def get(url, retries=3):
    for i in range(retries + 1):
        with _lock:
            gap = time.time() - _last[0]
            if gap < DELAY:
                time.sleep(DELAY - gap)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                with _lock:
                    _stats["ok"] += 1
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                with _lock:
                    _stats["skip"] += 1
                return None
            if i == retries:
                with _lock:
                    _stats["err"] += 1
                raise
            time.sleep((4 if e.code >= 500 else 2) * (i + 1))
        except Exception:
            if i == retries:
                with _lock:
                    _stats["err"] += 1
                raise
            time.sleep(2 * (i + 1))


def slugify(name):
    s = name.lower().replace("'", "").replace("\u2019", "").replace(".", "")
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# ---------------------------------------------------------------- 球员来源
def top_players(n):
    """世界排名前 n 名 → [{id,name_en,country,slug}]"""
    d = json.load(open(HERE_DASH, encoding="utf-8"))
    grp = next((g for g in d.get("rankings", [])
                if g.get("name_en") == "World Rankings"), None)
    if not grp:
        return []
    slug_map = {}
    if os.path.exists(SLUGS_CACHE):
        slug_map = json.load(open(SLUGS_CACHE, encoding="utf-8"))
    pos = grp["variants"][0]["positions"][:n]
    out = []
    for p in pos:
        nm = p.get("name_en", "")
        sid = p.get("playerId")
        slug = None
        hit = slug_map.get(nm)
        if hit and hit[0]:
            slug = hit[0]
        else:
            slug = slugify(nm)
        out.append({
            "id": sid, "name_en": nm,
            "name_zh": p.get("name_zh", nm),
            "country": p.get("country", ""),
            "slug": slug,
        })
    return out


# ---------------------------------------------------------------- 解析
def parse_h2h(html, slug_a, slug_b):
    """返回 (a_wins, b_wins, a_frames, b_frames, meetings[])"""
    # 以 data-match-id 切分每场，避免 fragile 的 div 嵌套切分
    blocks = re.split(r'(?=<div class="match row[^"]*"[^>]*data-match-id=")', html)
    a_wins = b_wins = a_frames = b_frames = 0
    meetings = []
    for blk in blocks:
        if 'player_1_name' not in blk and 'player_2_name' not in blk:
            continue
        # 双方 slug
        sa = re.search(r'player_1_name[^>]*>.*?/players/([a-z0-9-]+)/', blk, re.S)
        sb = re.search(r'player_2_name[^>]*>.*?/players/([a-z0-9-]+)/', blk, re.S)
        if not sa or not sb:
            continue
        sa, sb = sa.group(1), sb.group(1)
        # 双方局分
        sc1 = re.search(r'player_1_score[^>]*>\s*<b>\s*(\d+)', blk, re.S)
        sc2 = re.search(r'player_2_score[^>]*>\s*(\d+)', blk, re.S)
        if not sc1 or not sc2:
            m = re.search(r'class="player_1_score"[^>]*>\s*<b>\s*(\d+)', blk)
            m2 = re.search(r'class="player_2_score"[^>]*>(\d+)', blk)
            if not m or not m2:
                continue
            sc1, sc2 = m, m2
        f1, f2 = int(sc1.group(1)), int(sc2.group(1))
        # 赛程/轮次/日期
        rnd = re.search(r'class="[^"]*round_name[^"]*"[^>]*>\s*<h5>(.*?)</h5>', blk, re.S)
        rnd = re.sub(r"<[^>]+>", "", rnd.group(1)).strip() if rnd else ""
        tour = re.search(r'class="topMargin bottomMargin red"[^>]*>.*?/tournaments/([a-z0-9-]+)/\d+[^"]*"[^>]*>(.*?)</a>', blk, re.S)
        tname = re.sub(r"<[^>]+>", "", tour.group(2)).strip() if tour else ""
        date = re.search(r'played_on[^>]*>\s*(\d{4}-\d{2}-\d{2})', blk)
        date = date.group(1) if date else ""
        # 谁赢：按 slug 定位（列表可能把胜者排在 player_1）
        if sa == slug_a:
            af, bf, aw = f1, f2, f1 > f2
        elif sa == slug_b:
            af, bf, aw = f2, f1, f2 > f1
        else:
            af, bf, aw = f1, f2, f1 > f2
        a_frames += af
        b_frames += bf
        if aw:
            a_wins += 1
        else:
            b_wins += 1
        meetings.append({
            "date": date, "tournament": tname, "round": rnd,
            "a_score": af, "b_score": bf, "a_win": aw,
        })
    meetings.sort(key=lambda x: (x["date"] or ""), reverse=True)
    return a_wins, b_wins, a_frames, b_frames, meetings


# ---------------------------------------------------------------- 抓取单对
def fetch_pair(a, b):
    key = "__".join(sorted([a["slug"], b["slug"]]))
    cf = os.path.join(CACHE, key + ".json")
    if os.path.exists(cf):
        return json.load(open(cf, encoding="utf-8"))
    html = get(f"{BASE}/head-to-head/{a['slug']}/{b['slug']}")
    rec = {"slug_a": a["slug"], "slug_b": b["slug"],
           "a_wins": 0, "b_wins": 0, "a_frames": 0, "b_frames": 0, "meetings": []}
    if html:
        aw, bw, af, bf, mt = parse_h2h(html, a["slug"], b["slug"])
        rec.update(a_wins=aw, b_wins=bw, a_frames=af, b_frames=bf,
                   meetings=mt[:10])
    json.dump(rec, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    return rec


# ---------------------------------------------------------------- 主流程
def main():
    players = top_players(TOP)
    print(f"前 {TOP} 名球员：{len(players)} 人", flush=True)
    # 去重 slug（同名不同人跳过）
    seen = set()
    players = [p for p in players if p["slug"] and p["slug"] not in seen
               and not seen.add(p["slug"])]
    pairs = [(players[i], players[j])
             for i in range(len(players))
             for j in range(i + 1, len(players))]
    print(f"待抓交手对：{len(pairs)} 对", flush=True)

    results = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for n, rec in enumerate(ex.map(fetch_pair,
                                       [p[0] for p in pairs],
                                       [p[1] for p in pairs]), 1):
            a, b = pairs[n - 1]
            key = "__".join(sorted([a["slug"], b["slug"]]))
            results[key] = {"a": a, "b": b}
            if n % 40 == 0:
                el = time.time() - t0
                print(f"  {n}/{len(pairs)}  ({el:.0f}s, 剩 {el/n*(len(pairs)-n):.0f}s) "
                      f"http={_stats}", flush=True)

    # 组装输出：pairs 以 sorted-slug 为键，附带双方信息与战绩
    out_pairs = {}
    for key, rb in results.items():
        rec = json.load(open(os.path.join(CACHE, key + ".json"), encoding="utf-8"))
        out_pairs[key] = {
            "slug_a": rb["a"]["slug"], "slug_b": rb["b"]["slug"],
            "name_a": rb["a"]["name_en"], "name_b": rb["b"]["name_en"],
            "a_wins": rec["a_wins"], "b_wins": rec["b_wins"],
            "a_frames": rec["a_frames"], "b_frames": rec["b_frames"],
            "meetings": rec["meetings"],
        }
    out = {
        "meta": {
            "source": "cuetracker.net",
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S"),
            "top": len(players), "pairs": len(out_pairs), "http": _stats,
        },
        "players": [
            {"id": p["id"], "name_en": p["name_en"], "name_zh": p["name_zh"],
             "country": p["country"], "slug": p["slug"]}
            for p in players
        ],
        "pairs": out_pairs,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.H2H_DATA=")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"\n完成：{len(out_pairs)} 对交手，球员 {len(players)} 人，http={_stats}")
    print(f"输出：{OUT_JSON} / {OUT_JS}")


if __name__ == "__main__":
    main()
