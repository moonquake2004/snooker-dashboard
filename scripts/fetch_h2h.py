#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取球员两两「生涯交手记录 H2H」—— 数据源 CueTracker。

CueTracker 页面结构（已核实，注意与早期版本的区别）：
  交手页：https://cuetracker.net/head-to-head/{slugA}/{slugB}
  「Past Matches」区是「一条赛事标题 + 其后的若干场比赛」重复排列：
      <p class="topMargin bottomMargin red"><b>…<a href="/tournaments/xxx/2026/7889">
        2026 Wuhan Open</a></b><i> - <span class="small">Professional Ranking</span></i></p>
      <div class="match row" data-match-id="…"> 一场比赛 </div>
      <div class="match row" data-match-id="…"> 同一赛事的另一场 </div>
      <p class="topMargin bottomMargin red">…下一个赛事…</p>
      …
  ⚠ 关键点：赛事标题在「其所辖比赛之前」，且一场赛事可能带多场比赛。
    因此必须「顺序扫描」维护当前赛事，不能在单个 match 块内向后正则搜索——
    那样会把赛事名整体错配到下一场（2026-08 之前的版本正是这个 bug，
    156/1910 条赛事名为空就是它回绕造成的）。

抓取策略：
  - 取世界排名前 N 名球员（来自 data/dashboard.json 的 World Rankings），解析 CueTracker slug
  - 两两组合 C(n,2) 对，各抓一次 H2H 页
  - 限流：并发 2、间隔 0.8s（与 fetch_titles.py 一致，CueTracker 密集请求会返 500）
  - 落盘缓存 data/raw/h2h_raw/（已 gitignore），重跑只补缺失

产物（分开是为了控制首屏体积）：
  data/h2h.json          摘要（JSON，便于排查）：meta + players + pairs 战绩
  data/h2h.js            摘要（随页面加载）：window.H2H_DATA
  data/h2h_meetings.js   逐场明细（打开交手页时按需加载）：window.H2H_MEETINGS
                         前 64 名全量约 2000 对；--meetings 0 时逐场全量可能数 MB，
                         故独立文件、打开交手页时才按 HTTP 注入，不进首屏

用法：
  python3 scripts/fetch_h2h.py                # 默认前 64 名
  python3 scripts/fetch_h2h.py --top 8        # 小样本试跑
  python3 scripts/fetch_h2h.py --top 32 --meetings 0 --workers 3 --delay 0.6

注意：本脚本属「全量刷新」（refresh.sh），不进轻量刷新 refresh_live.sh——
      H2H 是生涯统计，无需每日追更，符合用户「只更新进行中赛事」的偏好。
"""

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import translations as T  # noqa: E402

BASE = "https://cuetracker.net"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

RAW = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(RAW, "h2h_raw")
os.makedirs(CACHE, exist_ok=True)
OUT_JSON = os.path.join(ROOT, "data", "h2h.json")
OUT_JS = os.path.join(ROOT, "data", "h2h.js")
OUT_MEET_JS = os.path.join(ROOT, "data", "h2h_meetings.js")
HERE_DASH = os.path.join(ROOT, "data", "dashboard.json")
SLUGS_CACHE = os.path.join(RAW, "titles_cache", "_slugs.json")

_lock = __import__("threading").Lock()
_last = [0.0]
_stats = {"ok": 0, "err": 0, "skip": 0}

# ---------------------------------------------------------------- 正则
TOUR_HEAD_RE = re.compile(r'<p class="topMargin bottomMargin red"[^>]*>')
MATCH_HEAD_RE = re.compile(r'<div class="match row[^"]*"[^>]*data-match-id="')
TOUR_LINK_RE = re.compile(r'/tournaments/([a-z0-9-]+)/(\d+)[^"]*"[^>]*>(.*?)</a>', re.S)
ROUND_RE = re.compile(r'class="[^"]*round_name[^"]*"[^>]*>\s*<h5>(.*?)</h5>', re.S)
DATE_RE = re.compile(r'played_on[^>]*>\s*(\d{4}-\d{2}-\d{2})')
P1_RE = re.compile(r'player_1_name[^>]*>.*?/players/([a-z0-9-]+)/', re.S)
P2_RE = re.compile(r'player_2_name[^>]*>.*?/players/([a-z0-9-]+)/', re.S)
S1_RE = re.compile(r'player_1_score[^>]*>\s*<b>\s*(\d+)', re.S)
S2_RE = re.compile(r'player_2_score[^>]*>\s*(\d+)', re.S)


def get(url, retries=4):
    """带退避重试的 GET，返回 (ok, html)。

    CueTracker 偶尔会在传输中途断开（http.client.IncompleteRead），
    这类错误必须重试而不是让整个抓取任务挂掉——前 64 名有 2000 多对，
    单对失败不该中断全局。

      (True,  html) 成功
      (True,  None) 404，页面确实不存在 → 结论确定，可缓存
      (False, None) 重试耗尽 → 不缓存，下次重跑自动补
    """
    for i in range(retries + 1):
        with _lock:
            gap = time.time() - _last[0]
            if gap < DELAY:
                time.sleep(DELAY - gap)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                # 沙箱代理对「无 Content-Length 的 chunked 传输」会在中途截断，
                # 触发 http.client.IncompleteRead。显式要 gzip 后响应带
                # Content-Encoding，体积从 ~568KB 降到 ~29KB，代理不再截断。
                "Accept-Encoding": "gzip",
            })
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
            with _lock:
                _stats["ok"] += 1
            return True, data.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                with _lock:
                    _stats["skip"] += 1
                return True, None
            if i == retries:
                with _lock:
                    _stats["err"] += 1
                return False, None
            time.sleep((4 if e.code >= 500 else 2) * (i + 1))
        except Exception:
            # 连接被重置 / 传输中断 / 超时：退避后重试
            if i == retries:
                with _lock:
                    _stats["err"] += 1
                return False, None
            time.sleep(2 * (i + 1))
    return False, None


def slugify(name):
    s = name.lower().replace("'", "").replace("\u2019", "").replace(".", "")
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9-]+", "-", s).strip("-")


def clean(s):
    """去标签 + 反转义 + 压空白"""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = (s.replace("&#039;", "'").replace("&amp;", "&")
          .replace("&nbsp;", " ").replace("&rsquo;", "\u2019")
          .replace("&quot;", '"'))
    return re.sub(r"\s+", " ", s).strip()


def tour_zh(name_en):
    """'2024 Players Championship' → '2024 球员锦标赛'（保留年份，便于区分同名赛事）"""
    s = (name_en or "").strip()
    m = re.match(r"^(\d{4})\s+(.*)$", s)
    if m:
        return f"{m.group(1)} {T.event_zh(m.group(2))}"
    return T.event_zh(s)


# ---------------------------------------------------------------- 球员来源
def top_players(n):
    """世界排名前 n 名 → [{id,name_en,name_zh,country,slug,rank}]"""
    d = json.load(open(HERE_DASH, encoding="utf-8"))
    grp = next((g for g in d.get("rankings", [])
                if g.get("name_en") == "World Rankings"), None)
    if not grp:
        return []
    slug_map = {}
    if os.path.exists(SLUGS_CACHE):
        slug_map = json.load(open(SLUGS_CACHE, encoding="utf-8"))
    out = []
    for i, p in enumerate(grp["variants"][0]["positions"][:n], 1):
        nm = p.get("name_en", "")
        hit = slug_map.get(nm)
        slug = hit[0] if (hit and hit[0]) else slugify(nm)
        out.append({
            "id": p.get("playerId"), "name_en": nm,
            "name_zh": p.get("name_zh", nm),
            "country": p.get("country", ""),
            "slug": slug, "rank": i,
        })
    return out


# ---------------------------------------------------------------- 解析
def parse_h2h(html, slug_a, slug_b):
    """顺序扫描「赛事标题 → 其辖下比赛」，返回 (a_wins, b_wins, a_frames, b_frames, meetings[])

    meetings 每项：
      date 比赛日期 / e 赛事英文名 / z 赛事中文名 / r 轮次英文 / rz 轮次中文
      as bs 以 slug_a 为视角的局分 / aw 是否 slug_a 获胜
    """
    idx = html.find("Past Matches")
    seg = html[idx:] if idx >= 0 else html

    marks = [(m.start(), 0) for m in TOUR_HEAD_RE.finditer(seg)]
    marks += [(m.start(), 1) for m in MATCH_HEAD_RE.finditer(seg)]
    marks.sort()
    if not marks:
        return 0, 0, 0, 0, []
    marks.append((len(seg), -1))

    a_wins = b_wins = a_frames = b_frames = 0
    meetings = []
    cur_tour = ""

    for i in range(len(marks) - 1):
        pos, kind = marks[i]
        chunk = seg[pos:marks[i + 1][0]]

        # ---- 赛事标题：更新「当前赛事」，供其后的比赛使用
        if kind == 0:
            m = TOUR_LINK_RE.search(chunk)
            cur_tour = clean(m.group(3)) if m else ""
            if not cur_tour:
                cur_tour = clean(chunk)
            continue

        # ---- 一场比赛
        sa = P1_RE.search(chunk)
        sb = P2_RE.search(chunk)
        s1 = S1_RE.search(chunk)
        s2 = S2_RE.search(chunk)
        if not (sa and sb and s1 and s2):
            continue
        f1, f2 = int(s1.group(1)), int(s2.group(1))

        rnd_m = ROUND_RE.search(chunk)
        rnd = clean(rnd_m.group(1)) if rnd_m else ""
        date_m = DATE_RE.search(chunk)
        date = date_m.group(1) if date_m else ""

        # 以 slug_a 的视角归一化（列表里胜者可能被排成 player_1）
        if sa.group(1) == slug_a:
            af, bf = f1, f2
        elif sa.group(1) == slug_b:
            af, bf = f2, f1
        else:
            af, bf = f1, f2
        aw = af > bf
        a_frames += af
        b_frames += bf
        if aw:
            a_wins += 1
        else:
            b_wins += 1

        meetings.append({
            "date": date,
            "e": cur_tour, "z": tour_zh(cur_tour),
            "r": rnd, "rz": T.round_zh(rnd),
            "as": af, "bs": bf, "aw": aw,
        })

    meetings.sort(key=lambda x: (x["date"] or ""), reverse=True)
    return a_wins, b_wins, a_frames, b_frames, meetings


# ---------------------------------------------------------------- 抓取单对
def fetch_pair(a, b):
    """抓一对交手；命中缓存直接返回，抓取失败返回 None（不落盘，留给下次重跑）。"""
    key = "__".join(sorted([a["slug"], b["slug"]]))
    cf = os.path.join(CACHE, key + ".json")
    if os.path.exists(cf):
        return json.load(open(cf, encoding="utf-8"))
    ok, html = get(f"{BASE}/head-to-head/{a['slug']}/{b['slug']}")
    if not ok:
        return None
    rec = {"slug_a": a["slug"], "slug_b": b["slug"],
           "a_wins": 0, "b_wins": 0, "a_frames": 0, "b_frames": 0, "meetings": []}
    if html:
        aw, bw, af, bf, mt = parse_h2h(html, a["slug"], b["slug"])
        rec.update(a_wins=aw, b_wins=bw, a_frames=af, b_frames=bf, meetings=mt)
    json.dump(rec, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    return rec


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="抓取 CueTracker 生涯交手记录 H2H")
    ap.add_argument("--top", type=int, default=64,
                    help="取世界排名前 N 名（默认 64，两两组合 C(N,2) 对）")
    ap.add_argument("--workers", type=int, default=2, help="并发数（默认 2）")
    ap.add_argument("--delay", type=float, default=0.8, help="请求最小间隔秒（默认 0.8）")
    ap.add_argument("--meetings", type=int, default=0,
                    help="每对保留的逐场明细条数（默认 0=保留全部，不限条数；>0 则截断到该值）")
    ap.add_argument("--no-fetch", action="store_true",
                    help="仅用 data/raw/h2h_raw 缓存组装输出，不发起网络抓取（断网/先发布已完成部分时用）")
    args = ap.parse_args()

    global DELAY
    DELAY = args.delay

    players = top_players(args.top)
    seen = set()
    players = [p for p in players if p["slug"] and p["slug"] not in seen
               and not seen.add(p["slug"])]
    pairs = [(players[i], players[j])
             for i in range(len(players))
             for j in range(i + 1, len(players))]
    print(f"前 {args.top} 名球员：{len(players)} 人 → 待抓 {len(pairs)} 对 "
          f"（并发 {args.workers}，间隔 {args.delay}s）", flush=True)

    t0 = time.time()
    failed = []
    if not args.no_fetch:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for n, rec in enumerate(ex.map(fetch_pair,
                                           [p[0] for p in pairs],
                                           [p[1] for p in pairs]), 1):
                if rec is None:
                    a, b = pairs[n - 1]
                    failed.append("__".join(sorted([a["slug"], b["slug"]])))
                if n % 100 == 0 or n == len(pairs):
                    el = time.time() - t0
                    print(f"  {n}/{len(pairs)}  ({el:.0f}s, 预计还剩 "
                          f"{el/n*(len(pairs)-n):.0f}s) http={_stats} "
                          f"失败={len(failed)}", flush=True)
    else:
        print("（--no-fetch：仅用本地缓存组装，跳过网络抓取）", flush=True)

    # 组装：跳过从未交手的组合（0 场），前端会提示「暂无交手记录」
    out_pairs, out_meet = {}, {}
    n_meet = 0
    untranslated = {}
    for a, b in pairs:
        key = "__".join(sorted([a["slug"], b["slug"]]))
        cf = os.path.join(CACHE, key + ".json")
        if not os.path.exists(cf):
            continue
        rec = json.load(open(cf, encoding="utf-8"))
        if not rec["meetings"]:
            continue
        # 缓存里 a/b 的顺序与 sorted-key 一致，统一成 [a 胜, b 胜, a 局, b 局]
        if rec["slug_a"] != key.split("__")[0]:
            aw, bw = rec["b_wins"], rec["a_wins"]
            af, bf = rec["b_frames"], rec["a_frames"]
            flip = True
        else:
            aw, bw = rec["a_wins"], rec["b_wins"]
            af, bf = rec["a_frames"], rec["b_frames"]
            flip = False
        out_pairs[key] = [aw, bw, af, bf]

        ms = rec["meetings"] if not args.meetings else rec["meetings"][:args.meetings]
        out_meet[key] = [
            {"date": m["date"], "e": m["e"], "z": m["z"],
             "r": m["r"], "rz": m["rz"],
             # 统一成 sorted-key 视角；前端按选择方向再翻一次
             "as": (m["bs"] if flip else m["as"]),
             "bs": (m["as"] if flip else m["bs"]),
             "aw": (not m["aw"] if flip else m["aw"])}
            for m in ms
        ]
        n_meet += len(ms)
        for m in ms:
            if m["z"] == m["e"]:
                untranslated[m["e"]] = untranslated.get(m["e"], 0) + 1

    out = {
        "meta": {
            "source": "cuetracker.net",
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S"),
            "top": len(players), "pairs": len(out_pairs),
            "meetings": n_meet, "meetingsPerPair": (args.meetings or "all"),
            "http": _stats,
        },
        "players": [
            {"slug": p["slug"], "en": p["name_en"], "zh": p["name_zh"],
             "c": p["country"], "rk": p["rank"]}
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
    with open(OUT_MEET_JS, "w", encoding="utf-8") as f:
        f.write("window.H2H_MEETINGS=")
        json.dump(out_meet, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    print(f"\n完成：{len(out_pairs)} 对有过交手（跳过未交手 "
          f"{len(pairs)-len(out_pairs)} 对），逐场明细 {n_meet} 条，http={_stats}")
    kb = lambda p: os.path.getsize(p) / 1024
    print(f"输出：h2h.js {kb(OUT_JS):.0f}KB / h2h_meetings.js {kb(OUT_MEET_JS):.0f}KB "
          f"/ h2h.json {kb(OUT_JSON):.0f}KB")
    if failed:
        print(f"⚠ {len(failed)} 对抓取失败（未缓存，重跑本脚本即可续抓），前 15 个：")
        for k in failed[:15]:
            print("     " + k)
        print("  续抓命令：python3 scripts/fetch_h2h.py --top "
              f"{args.top} --meetings {args.meetings}")
    if untranslated:
        top_un = sorted(untranslated.items(), key=lambda x: -x[1])[:15]
        print(f"⚠ 未汉化赛事名 {len(untranslated)} 种（合计 "
              f"{sum(untranslated.values())} 条），最常见：")
        for k, v in top_un:
            print(f"     {v:>4}  {k}")


if __name__ == "__main__":
    main()
