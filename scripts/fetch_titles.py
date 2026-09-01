#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 CueTracker 抓取球员生涯夺冠清单，生成 data/raw/titles.json。

背景：维基百科的「排名赛冠军榜」页面在本机网络不可达，且其数据停留在 2021 年。
CueTracker 是斯诺克最全的战绩数据库，覆盖 1970 年代至今的全部职业赛事且持续更新，
故改用其作为生涯冠军数据源。

接口（服务端渲染 HTML，无需登录）：
  https://cuetracker.net/players/{slug}/finishes/professional/{category}/winner/all-time
  category: total / ranking / minor-ranking / non-ranking / league / invitational / ...

  分类关系（奥沙利文实测）：total 80 = ranking 41 + invitational 25 + league 10
                                      + minor-ranking 3 + non-ranking 1
  本脚本只取 total 与 ranking，非排名赛冠军 = total - ranking。

候选球员来源：
  1. WST 数据里出现过的现役球员（players.json + matches.json 中的额外球员）
  2. 手工维护的 LEGACY 名单（已退役或不在 WST 名单中的冠军球员）

抓取结果按 slug 落盘缓存，重跑只补缺失项。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

BASE = "https://cuetracker.net"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "raw", "titles.json")
CACHE = os.path.join(ROOT, "data", "raw", "titles_cache")
os.makedirs(CACHE, exist_ok=True)

WORKERS = 2      # 并发要压住，CueTracker 对密集请求会返回 500
DELAY = 0.8

# ---------------------------------------------------------------- 历史名宿
# WST 现役名单里没有、但拿过职业冠军的球员（含 1970-80 年代）
LEGACY = {
    "Ray Reardon": "Wales", "John Spencer": "England", "Alex Higgins": "Northern Ireland",
    "Terry Griffiths": "Wales", "Cliff Thorburn": "Canada", "Dennis Taylor": "Northern Ireland",
    "Steve Davis": "England", "Jimmy White": "England", "Willie Thorne": "England",
    "Tony Knowles": "England", "Tony Meo": "England", "Neal Foulds": "England",
    "Silvino Francisco": "South Africa", "Joe Johnson": "England",
    "John Parrott": "England", "Mike Hallett": "England",
    "Stephen Hendry": "Scotland", "James Wattana": "Thailand", "Peter Ebdon": "England",
    "Ken Doherty": "Ireland", "Paul Hunter": "England", "Alan McManus": "Scotland",
    "Darren Morgan": "Wales", "Nigel Bond": "England", "Dave Harold": "England",
    "Andy Hicks": "England", "Dominic Dale": "Wales", "Anthony Hamilton": "England",
    "Fergal O'Brien": "Ireland", "Gerard Greene": "Northern Ireland",
    "Michael Judge": "Ireland", "Mark King": "England", "Jamie Burnett": "Scotland",
    "Marcus Campbell": "Scotland", "Rory McLeod": "England", "Barry Pinches": "England",
    "Joe Swail": "Northern Ireland", "Rod Lawler": "England", "Ben Woollaston": "England",
    "Andrew Higginson": "England", "Tony Drago": "Malta", "Troy Shaw": "England",
    "Ju Reti": "Finland", "Michael White": "Wales", "Stephen Lee": "England",
    "Graeme Dott": "Scotland", "Ian McCulloch": "England", "Michael Holt": "England",
    "Mark Davis": "England", "David Gray": "England", "Stuart Pettman": "England",
    "Ricky Walden": "England", "Marco Fu": "Hong Kong", "Liang Wenbo": "China",
    "Yan Bingtao": "China", "Cao Yupeng": "China", "Mei Xiwen": "China",
    "Fan Zhengyi": "China", "Pang Junxu": "China", "Zhao Xintong": "China",
    "Xiao Guodong": "China", "Zhou Yuelong": "China", "Lyu Haotian": "China",
    "Si Jiahui": "China", "Wu Yize": "China", "Zhang Anda": "China",
    "Yuan Sijun": "China", "Xu Si": "China", "Chen Feilong": "China",
    "Tian Pengfei": "China", "Li Hang": "China", "Jak Jones": "Wales",
    "Jamie Jones": "Wales", "Hossein Vafaei": "Iran", "Noppon Saengkham": "Thailand",
    "Thepchaiya Un-Nooh": "Thailand", "Akani Songsermsawad": "Thailand",
    "Luca Brecel": "Belgium", "Chris Wakelin": "England", "Robert Milkins": "England",
    "Matthew Selt": "England", "Elliot Slessor": "England", "Daniel Wells": "Wales",
    "Joe O'Connor": "England", "Sam Craigie": "England", "Stuart Carrington": "England",
    "Jimmy Robertson": "England", "Scott Donaldson": "Scotland", "Jamie Clarke": "Wales",
    "David Grace": "England", "Mark Joyce": "England", "Liam Highfield": "England",
    "Robbie Williams": "England", "Kurt Maflin": "Norway", "Gary Wilson": "England",
    "Kyren Wilson": "England", "Neil Robertson": "Australia", "Mark Selby": "England",
    "John Higgins": "Scotland", "Mark Williams": "Wales", "Ronnie O'Sullivan": "England",
    "Stephen Maguire": "Scotland", "Judd Trump": "England", "Anthony McGill": "Scotland",
    "Ryan Day": "Wales", "Ali Carter": "England", "Barry Hawkins": "England",
    "Matthew Stevens": "Wales", "Joe Perry": "England", "Mark Allen": "Northern Ireland",
    "Martin Gould": "England", "Jamie Cope": "England", "Tom Ford": "England",
    "David Gilbert": "England", "Peter Lines": "England", "Alfie Burden": "England",
    "Craig Steadman": "England", "Ian Burns": "England", "Sam Baird": "England",
    "Adam Duffy": "England", "Zhang Yong": "China", "Chen Zifan": "China",
    "Zhao Jianbo": "China", "Michael Georgiou": "Cyprus", "Mitchell Mann": "England",
    "Oliver Lines": "England", "Lee Walker": "Wales", "Duane Jones": "Wales",
    "Jackson Page": "Wales", "Ashley Carty": "England", "Louis Heathcote": "England",
    "Xu Yi Chen": "China", "Chang Bingyu": "China", "Lei Peifan": "China",
    "Jiang Jun": "China", "Liu Hongyu": "China", "Ma Hailong": "China",
    "Gong Chenzhi": "China", "Huang Jiahao": "China", "Bai Langning": "China",
    "Peng Yisong": "China", "Chen Zhe": "China", "Ross Muir": "Scotland",
    "Michael Wasley": "England", "Chris Norbury": "England", "Tony Drago": "Malta",
    "Bo Ning": "China", "Ratchayothin Yotharuck": "Thailand", "Kritsanut Lertsattayathorn": "Thailand",
    "Thanawat Thirapongpaiboon": "Thailand", "Passakorn Suwannawat": "Thailand",
    "Amir Sarkhosh": "Iran", "Soheil Vahedi": "Iran", "Ali Ghareghouzlo": "Iran",
    "Mohammad Bilal": "Pakistan", "Babar Masih": "Pakistan", "Shahid Aftab": "Pakistan",
    "Thor Chuan Leong": "Malaysia", "Rory Thor": "Malaysia", "Lim Kok Leong": "Malaysia",
    "Moh Keen Hoo": "Malaysia", "Ka Wai Cheung": "Hong Kong", "Andy Lee": "Hong Kong",
    "Au Chi Wai": "Hong Kong", "Chan Wai Ki": "Hong Kong", "Fung Kwok Wai": "Hong Kong",
    "Mike Dunn": "England", "Gerard Greene": "Northern Ireland", "Sam Baird": "England",
    "Noppon Saengkham": "Thailand", "Zak Surety": "England", "Sanderson Lam": "England",
    "Hammad Miah": "England", "Sean O'Sullivan": "England", "Ryan Thomerson": "Australia",
    "Steve Mifsud": "Australia", "Vinnie Calabrese": "Australia", "James Mifsud": "Australia",
    "Adrian Ridley": "Australia", "Johl Younger": "Australia", "Shaun Dalitz": "Australia",
    "Robbie Foldvari": "Australia", "Warren King": "Australia", "John Campbell": "Australia",
    "Eddie Charlton": "Australia", "Horace Lindrum": "Australia", "Walter Lindrum": "Australia",
    "Fred Davis": "England", "Joe Davis": "England", "John Pulman": "England",
    "Rex Williams": "England", "Jackie Rea": "Northern Ireland", "Kingsley Kennerley": "England",
    "Sydney Lee": "England", "Alec Brown": "England", "Tom Newman": "England",
    "Clark McConachy": "New Zealand", "Murt O'Donoghue": "New Zealand",
    "Gary Owen": "Wales", "Harry Stokes": "Scotland",
    "Dene O'Kane": "New Zealand", "David Taylor": "England",
    "Murdo MacLeod": "Scotland", "Bert Demarco": "Scotland",
    "Eddie Sinclair": "Scotland", "Bill Werbeniuk": "Canada", "Kirk Stevens": "Canada",
    "Alain Robidoux": "Canada", "Jim Wych": "Canada", "Bob Chaperon": "Canada",
    "Gino Rigitano": "Canada", "Frank Jonik": "Canada", "Mario Morra": "Canada",
    "Jim Bear": "Canada", "Brady Gollan": "Canada", "Tom Finstad": "Canada",
    "Wayne Jones": "Wales", "Steve Newbury": "Wales", "Tony Chappel": "Wales",
    "Ray Edmonds": "England", "Paddy Browne": "Ireland", "Eugene Hughes": "Ireland",
    "Tommy Murphy": "Ireland", "Pascal Burke": "Ireland", "Jimmy van Rensberg": "South Africa",
    "Perrie Mans": "South Africa", "Peter Mans": "South Africa", "Mannie Francisco": "South Africa",
    "Jimmy van Rensburg": "South Africa", "Francois Ellis": "South Africa",
    "Ronnie Atkins": "Wales", "Clive Everton": "Wales", "Roy Andrewartha": "Wales",
    "Geoff Foulds": "England", "Graham Miles": "England", "John Virgo": "England",
    "Pat Houlihan": "England", "Bernard Bennett": "England", "Maurice Parkin": "England",
    "Doug Mountjoy": "Wales", "Ray Edmonds": "England", "Patsy Fagan": "Ireland",
    "John Dunning": "England", "Willie Jamieson": "Scotland", "Ian Anderson": "Australia",
    "Ian Williamson": "England", "Jon Wright": "England", "Steve Ventham": "England",
    "Danny Fowler": "England", "Barry West": "England", "Jack McLaughlin": "Northern Ireland",
    "Billy Kelly": "Ireland", "Sean Lanigan": "England", "Bob Harris": "England",
    "Jim Meadowcroft": "England", "Marcus Owen": "England", "Dave Martin": "England",
    "Jack Fitzmaurice": "England", "Bernard Mapp": "England", "John Barrie": "England",
}

# ---------------------------------------------------------------- 工具
_lock = __import__("threading").Lock()
_last = [0.0]
_stats = {"ok": 0, "404": 0, "err": 0}


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
                    _stats["404"] += 1
                return None
            if i == retries:
                with _lock:
                    _stats["err"] += 1
                raise
            # 5xx 多半是限流，拉长退避再试
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


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def parse_titles(html):
    if not html:
        return []
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = [clean(td) for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(tds) == 1 and re.match(r"^\d{4}\s+\S", tds[0]):
            out.append(tds[0])
    return out


def search_player(name):
    """用 CueTracker 的自动补全接口兜底解析 slug"""
    q = urllib.parse.quote(name.split()[-1])
    raw = get(f"{BASE}/searchplayer?query={q}")
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except Exception:
        return None
    best, score = None, 0.0
    low = name.lower()
    for it in items:
        r = SequenceMatcher(None, low, it["name"].lower()).ratio()
        if r > score:
            best, score = it, r
    if best and score >= 0.62:
        return best
    return None


def resolve_slug(name, cache):
    if name in cache:
        return cache[name]
    try:
        s = slugify(name)
        html = get(f"{BASE}/players/{s}/finishes/professional/total/winner/all-time")
        if html is not None:
            cache[name] = (s, "slugify")
            return cache[name]
        hit = search_player(name)
        if hit:
            cache[name] = (hit["id"], "search:" + hit["name"])
            return cache[name]
    except Exception as e:
        print(f"  [slug 解析失败] {name}: {e}", flush=True)
    cache[name] = (None, "unresolved")
    return cache[name]


# ---------------------------------------------------------------- 候选名单
def candidates():
    """WST 现役球员 + LEGACY 名宿，返回 [(name, country), ...]"""
    out = {}
    # 1) WST
    pj = os.path.join(ROOT, "data", "raw", "players.json")
    if os.path.exists(pj):
        with open(pj, encoding="utf-8") as f:
            for p in json.load(f):
                a = p.get("attributes", p)
                n = f"{a.get('firstName','')} {a.get('surname','')}".strip()
                if n:
                    out[n] = a.get("countryCode") or a.get("country") or ""
    # 2) 比赛数据里额外出现的球员
    sys.path.insert(0, HERE)
    try:
        import translations as T
        for n in getattr(T, "PLAYERS_EXTRA", {}):
            out.setdefault(n, "")
    except Exception:
        pass
    # 3) 名宿
    for n, c in LEGACY.items():
        out.setdefault(n, c)
    return out


# ---------------------------------------------------------------- 主流程
def main():
    names = candidates()
    print(f"候选球员 {len(names)} 人（WST 现役 {len(names) - len(LEGACY)} + 名宿名单 {len(LEGACY)}）",
          flush=True)

    slug_cache_path = os.path.join(CACHE, "_slugs.json")
    slug_cache = {}
    if os.path.exists(slug_cache_path):
        with open(slug_cache_path, encoding="utf-8") as f:
            slug_cache = json.load(f)

    todo = [n for n in names if n not in slug_cache]
    if todo:
        print(f"解析 slug：{len(todo)} 人待解析（{len(names) - len(todo)} 命中缓存）", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for i, name in enumerate(ex.map(lambda n: (n, resolve_slug(n, slug_cache)), todo), 1):
                pass
        # resolve_slug 写的是共享 dict，这里统一落盘
        with open(slug_cache_path, "w", encoding="utf-8") as f:
            json.dump(slug_cache, f, ensure_ascii=False, indent=1)

    unresolved = [n for n, (s, _) in slug_cache.items() if not s]
    print(f"slug 解析完成，失败 {len(unresolved)} 人", flush=True)
    if unresolved:
        print("  ", unresolved[:15], flush=True)

    # 抓取
    jobs = []
    seen = set()
    for name, (slug, how) in slug_cache.items():
        if not slug or slug in seen:
            continue
        seen.add(slug)
        jobs.append((slug, names.get(name, ""), how))

    def work(job):
        slug, country, how = job
        tf = os.path.join(CACHE, f"{slug}__total.json")
        rf = os.path.join(CACHE, f"{slug}__ranking.json")
        total = json.load(open(tf, encoding="utf-8")) if os.path.exists(tf) else None
        if total is None:
            total = parse_titles(get(f"{BASE}/players/{slug}/finishes/professional/total/winner/all-time"))
            if total is None:
                total = []
            json.dump(total, open(tf, "w", encoding="utf-8"), ensure_ascii=False)
        ranking = None
        if total:
            ranking = json.load(open(rf, encoding="utf-8")) if os.path.exists(rf) else None
            if ranking is None:
                ranking = parse_titles(get(f"{BASE}/players/{slug}/finishes/professional/ranking/winner/all-time"))
                if ranking is None:
                    ranking = []
                json.dump(ranking, open(rf, "w", encoding="utf-8"), ensure_ascii=False)
        return slug, country, how, total, ranking or []

    players = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for n, (slug, country, how, total, ranking) in enumerate(ex.map(work, jobs), 1):
            if total:
                players[slug] = {
                    "slug": slug,
                    "countryCode": country or "",
                    "match": how,
                    "total": total,
                    "ranking": ranking,
                }
            if n % 50 == 0:
                el = time.time() - t0
                print(f"  {n}/{len(jobs)}  有冠军 {len(players)}  "
                      f"({el:.0f}s, 剩 {el / n * (len(jobs) - n):.0f}s)", flush=True)

    # 补名字：用 search 命中的原名 / slug 还原
    data = {
        "meta": {
            "source": "cuetracker.net",
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S"),
            "candidates": len(jobs),
            "players_with_titles": len(players),
            "unresolved_names": unresolved,
            "http": _stats,
        },
        "players": players,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"\n完成：{len(players)} 名球员有职业冠军（请求 {_stats}）")
    print(f"输出：{OUT}")


if __name__ == "__main__":
    main()
