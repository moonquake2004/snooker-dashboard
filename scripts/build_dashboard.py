#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 data/raw/*.json 清洗、按赛季过滤、聚合为看板所需的单文件 data/dashboard.json。

产出结构：
  meta / season / tournaments / matches / players / rankings /
  centuries / leaderboards
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translations as T  # noqa: E402
import tournament_meta as M  # noqa: E402
import title_board as TB  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
OUT_PATH = os.path.join(BASE_DIR, "data", "dashboard.json")

SEASON_ID = 2026          # 2026/27 赛季
SEASON_LABEL = "2026/27"
IMG = "https://images.gc.wstservices.co.uk/fit-in/400x400/"

CST = timezone(timedelta(hours=8))


# ------------------------------------------------------------------ 工具
def load(name):
    with open(os.path.join(RAW_DIR, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def sval(v):
    return (str(v).strip() if v is not None else "")


def player_name_en(p):
    if not p:
        return ""
    first = sval(p.get("firstName"))
    sur = sval(p.get("surname"))
    return f"{first} {sur}".strip()


def brief_player(p):
    """从任意球员字典构造精简双語结构。"""
    if not p:
        return None
    en = player_name_en(p)
    zh = T.player_zh(en)
    code = sval(p.get("country"))
    media = p.get("media") or {}
    photo = media.get("profile") or ""
    return {
        "id": p.get("playerID") or p.get("id"),
        "name_en": en,
        "name_zh": zh or en,
        "country": code,
        "country_zh": T.country_code_zh(code),
        "country_en": T.country_code_en(code),
        "photo": f"{IMG}{photo}" if photo else "",
    }


def round_rank(r):
    """轮次深度，用于求「最好成绩」。越大越靠后。"""
    s = (r or "").lower()
    if not s:
        return 0
    if "final" in s and "semi" not in s and "quarter" not in s:
        return 100
    if "semi" in s:
        return 90
    if "quarter" in s:
        return 80
    m = re.search(r"round\s*(\d+)", s)
    if m:
        return int(m.group(1))
    if "last 16" in s:
        return 70
    if "last 32" in s:
        return 60
    if "last 64" in s:
        return 50
    if "last 128" in s:
        return 40
    if "league" in s or "stage" in s or "robin" in s:
        return 30
    if "wildcard" in s or "pre-qualifier" in s:
        return 10
    return 20


def main():
    print("读取原始数据 …")
    raw_seasons = load("seasons")
    raw_rankings = load("rankings")
    raw_tournaments = load("tournaments")
    raw_players = load("players")
    raw_matches = load("matches")

    # ---------------------------------------------------------- 赛季
    season_meta = next((s["attributes"] for s in raw_seasons
                        if s.get("id") == str(SEASON_ID)), {})
    print(f"  赛季：{season_meta.get('name', SEASON_LABEL)}")

    # ---------------------------------------------------------- 球员主表
    def new_player(pid, a):
        en = player_name_en(a)
        zh = T.player_zh(en)
        code = sval(a.get("country"))
        media = a.get("media") or {}
        photo = media.get("profile") or ""
        return {
            "id": pid,
            "name_en": en,
            "name_zh": zh or en,
            "has_zh": bool(zh),
            "nickname": sval(a.get("nickname")),
            "country": code,
            "country_zh": T.country_code_zh(code),
            "country_en": T.country_code_en(code),
            "dob": sval(a.get("dob")),
            "turnedPro": a.get("turnedPro"),
            "photo": f"{IMG}{photo}" if photo else "",
            "slug": sval(a.get("playerSlug")),
            # 赛季统计（下面填充）
            "matches": 0, "wins": 0, "losses": 0,
            "framesWon": 0, "framesLost": 0,
            "centuries": 0, "fiftyPlus": 0, "highestBreak": 0,
            "centuryRate": 0.0, "fiftyRate": 0.0,
            "titles": 0, "bestRound": "", "bestRoundRank": 0,
            "tournaments": [],
        }

    players = {}
    for item in raw_players:
        players[item["id"]] = new_player(item["id"], item["attributes"])

    def ensure_player(p):
        """对阵中出现的球员若不在主名单（业余/外卡），自动补登记。"""
        pid = p.get("playerID") or p.get("id")
        if not pid:
            return None
        if pid not in players:
            players[pid] = new_player(pid, p)
        return players[pid]

    # 预扫描：把本赛季对阵里出现的全部球员登记进来
    for item in raw_matches:
        a = item["attributes"]
        t = a.get("tournament") or {}
        if t.get("season") != SEASON_ID:
            continue
        for k in ("homePlayer", "awayPlayer"):
            if a.get(k):
                ensure_player(a[k])

    print(f"  球员：{len(players)}")

    # ---------------------------------------------------------- 赛事（本赛季）
    # 以 tournaments.json 为准（含尚未产生对阵的远期赛事），用日期范围筛赛季
    s_start = season_meta.get("tournaments", {}).get("first", "2026-06-01")
    s_end = season_meta.get("tournaments", {}).get("last", "2027-05-31")

    # 奖金：优先用官网抓取结果，抓不到则回退到手工兜底值
    prize_path = os.path.join(RAW_DIR, "prize_pages.json")
    prize_raw = {}
    if os.path.exists(prize_path):
        with open(prize_path, encoding="utf-8") as fh:
            prize_raw = json.load(fh)
        print(f"  官网奖金数据：{len(prize_raw)} 条")

    def prize_of(tid, core):
        bd = (prize_raw.get(tid) or {}).get("breakdown") or {}
        total = bd.get("总奖金")
        winner = bd.get("冠军")
        if total is None or winner is None:
            manual = M.MANUAL_PRIZE.get(core) or {}
            total = total if total is not None else manual.get("total")
            winner = winner if winner is not None else manual.get("winner")
        return total, winner

    tournaments = []
    for item in raw_tournaments:
        a = item["attributes"]
        sd = sval(a.get("startDate"))
        ed = sval(a.get("endDate"))
        if not sd or sd < s_start or sd > s_end:
            continue
        name_en = sval(a.get("name"))
        core = T.tournament_core(name_en)
        is_qual = bool(re.search(r"qualifiers?$", name_en, re.I))
        ttype = M.classify(core, is_qual)
        total, winner = prize_of(item["id"], core)
        tournaments.append({
            "id": item["id"],
            "name_en": name_en,
            "name_zh": T.tournament_zh(name_en),
            "core": core,
            "type": ttype,
            "type_zh": M.TYPE_ZH.get(ttype, ""),
            "type_en": M.TYPE_EN.get(ttype, ""),
            "tripleCrown": (not is_qual) and M.is_triple_crown(core),
            "prizeTotal": total,
            "prizeWinner": winner,
            "startDate": sd,
            "endDate": ed,
            "city_en": sval(a.get("city")),
            "city_zh": T.city_zh(a.get("city")),
            "country_en": sval(a.get("country")),
            "country_zh": T.country_zh(a.get("country")),
            "isQualifier": is_qual,
            "matchCount": a.get("matchCount") or 0,
            "logo": f"{IMG}{a['tournamentListingImage']}"
                    if a.get("tournamentListingImage") else "",
            "infoPage": sval(a.get("informationPage")),
            "status": "upcoming",
            "completedMatches": 0,
            "winner": None, "runnerUp": None, "finalScore": "",
            "winnerOfficial": sval(a.get("winner")),
        })
    tournaments.sort(key=lambda t: (t["startDate"], t["name_en"]))
    tmap = {t["id"]: t for t in tournaments}
    print(f"  赛季赛事：{len(tournaments)}")

    # ---------------------------------------------------------- 比赛（本赛季）
    matches, centuries = [], []
    today = datetime.now(CST).strftime("%Y-%m-%d")

    for item in raw_matches:
        a = item["attributes"]
        t = a.get("tournament") or {}
        tid = t.get("tournamentID") or a.get("tournamentID")
        if tid not in tmap:
            continue

        home = brief_player(a.get("homePlayer"))
        away = brief_player(a.get("awayPlayer"))
        rnd = sval(a.get("round"))
        status = sval(a.get("status"))
        hs = a.get("homePlayerScore") or 0
        as_ = a.get("awayPlayerScore") or 0
        dt = sval(a.get("startDateTime"))

        # 逐局数据 → 单杆统计
        hist = (a.get("history") or {}).get("matchData") or {}
        frames = (hist.get("matchHistory") or {}).get("frames") or []
        frame_rows = []
        for f in frames:
            hp = f.get("homePlayerPoints") or 0
            ap = f.get("awayPlayerPoints") or 0
            hb = f.get("homePlayerFiftyPlusBreaks") or 0
            ab = f.get("awayPlayerFiftyPlusBreaks") or 0
            frame_rows.append([f.get("frameNumber"), hp, ap, hb, ab])
            for who, brk in (("home", hb), ("away", ab)):
                if brk >= 100 and (who == "home" and home or
                                   who == "away" and away):
                    pl = home if who == "home" else away
                    centuries.append({
                        "player": pl["name_en"],
                        "player_zh": pl["name_zh"],
                        "playerId": pl["id"],
                        "country": pl["country"],
                        "country_zh": pl["country_zh"],
                        "value": brk,
                        "tournamentId": tid,
                        "tournament_en": tmap[tid]["name_en"],
                        "tournament_zh": tmap[tid]["name_zh"],
                        "opponent_en": (away if who == "home" else home)["name_en"],
                        "opponent_zh": (away if who == "home" else home)["name_zh"],
                        "date": dt[:10],
                        "round_en": rnd,
                        "round_zh": T.round_zh(rnd),
                    })

        rec = {
            "id": item["id"],
            "tournamentId": tid,
            "tournament_en": tmap[tid]["name_en"],
            "tournament_zh": tmap[tid]["name_zh"],
            "round_en": rnd,
            "round_zh": T.round_zh(rnd),
            "roundRank": round_rank(rnd),
            "date": dt[:10],
            "time": dt[11:16] if len(dt) >= 16 else "",
            "status": status,
            "status_zh": T.status_zh(status),
            "home": home,
            "away": away,
            "homeScore": hs,
            "awayScore": as_,
            "frames": a.get("numberOfFrames"),
            "winnerId": (home or {}).get("id") if hs > as_ else
                        ((away or {}).get("id") if as_ > hs else None),
            "frames_detail": frame_rows,
        }
        matches.append(rec)

        # 赛事进度
        tt = tmap[tid]
        if status == "Completed":
            tt["completedMatches"] += 1

        # 球员赛季统计
        for side, opp, sc, osc in ((home, away, hs, as_), (away, home, as_, hs)):
            if not side or not side["id"]:
                continue
            pl = players.get(side["id"])
            if pl is None:
                continue
            if status != "Completed":
                continue
            pl["matches"] += 1
            pl["framesWon"] += sc
            pl["framesLost"] += osc
            if sc > osc:
                pl["wins"] += 1
            else:
                pl["losses"] += 1
            rk = round_rank(rnd)
            if rk > pl["bestRoundRank"]:
                pl["bestRoundRank"] = rk
                pl["bestRound"] = T.round_zh(rnd)
                pl["bestRound_en"] = rnd

    # 逐局：50+ / 破百 / 最高单杆（按球员聚合，避免重复统计未分配的对阵）
    for rec in matches:
        if rec["status"] != "Completed":
            continue
        for idx, side in ((3, rec["home"]), (4, rec["away"])):
            if not side or not side["id"]:
                continue
            pl = players.get(side["id"])
            if pl is None:
                continue
            for fr in rec["frames_detail"]:
                brk = fr[idx]
                if brk >= 100:
                    pl["centuries"] += 1
                    pl["fiftyPlus"] += 1
                elif brk >= 50:
                    pl["fiftyPlus"] += 1
                if brk > pl["highestBreak"]:
                    pl["highestBreak"] = brk

    # 破百率 / 50+ 率（按「出场总局数」= framesWon+framesLost 折算成百分比，
    # 单杆与局一一对应，故比率恒 ≤100%，比「按场」更直观；数据直接派生，无需额外抓取）
    for pl in players.values():
        frames = pl["framesWon"] + pl["framesLost"]
        if frames > 0:
            pl["centuryRate"] = round(pl["centuries"] / frames * 100, 1)
            pl["fiftyRate"] = round(pl["fiftyPlus"] / frames * 100, 1)
        else:
            pl["centuryRate"] = 0.0
            pl["fiftyRate"] = 0.0

    # 每站冠军 / 亚军 / 决赛比分
    for rec in matches:
        if rec["round_en"] != "Final" or rec["status"] != "Completed":
            continue
        tt = tmap[rec["tournamentId"]]
        home_win = rec["homeScore"] > rec["awayScore"]
        tt["winner"] = rec["home"] if home_win else rec["away"]
        tt["runnerUp"] = rec["away"] if home_win else rec["home"]
        tt["finalScore"] = (f"{rec['homeScore']}-{rec['awayScore']}"
                            if home_win else
                            f"{rec['awayScore']}-{rec['homeScore']}")
        wid = tt["winner"]["id"] if tt["winner"] else None
        if wid in players:
            players[wid]["titles"] += 1

    # 赛事状态
    for tt in tournaments:
        if tt["completedMatches"] > 0 and tt["startDate"] <= today:
            tt["status"] = ("completed"
                            if tt["endDate"] < today or tt["winner"]
                            else "ongoing")
        elif tt["startDate"] <= today <= tt["endDate"]:
            tt["status"] = "ongoing"
        else:
            tt["status"] = "upcoming"

    print(f"  赛季比赛：{len(matches)}｜单杆破百：{len(centuries)}")

    # ---------------------------------------------------------- 球员参与赛事
    for rec in matches:
        if rec["status"] != "Completed":
            continue
        for side in (rec["home"], rec["away"]):
            if not side or not side["id"]:
                continue
            pl = players.get(side["id"])
            if pl is None:
                continue
            found = next((x for x in pl["tournaments"]
                          if x["id"] == rec["tournamentId"]), None)
            if found is None:
                found = {
                    "id": rec["tournamentId"],
                    "name_en": rec["tournament_en"],
                    "name_zh": rec["tournament_zh"],
                    "bestRound": "", "bestRound_en": "", "bestRank": 0,
                }
                pl["tournaments"].append(found)
            if rec["roundRank"] > found["bestRank"]:
                found["bestRank"] = rec["roundRank"]
                found["bestRound"] = rec["round_zh"]
                found["bestRound_en"] = rec["round_en"]

    for pl in players.values():
        pl["tournaments"].sort(key=lambda x: -x["bestRank"])
        pl.pop("bestRoundRank", None)

    # 决赛结果：区分冠军 / 亚军，否则 Event By Event 里所有决赛都只显示"决赛"
    for pl in players.values():
        has_winner = has_runner = False
        for tentry in pl["tournaments"]:
            tt = tmap.get(tentry["id"])
            if not tt:
                continue
            wid = tt.get("winner", {}).get("id") if tt.get("winner") else None
            rid = tt.get("runnerUp", {}).get("id") if tt.get("runnerUp") else None
            if tentry.get("bestRound_en") == "Final":
                if wid == pl["id"]:
                    tentry["finalResult"] = "winner"
                    has_winner = True
                elif rid == pl["id"]:
                    tentry["finalResult"] = "runner-up"
                    has_runner = True
        if has_winner:
            pl["bestFinalResult"] = "winner"
        elif has_runner:
            pl["bestFinalResult"] = "runner-up"

    # ---------------------------------------------------------- 排名榜
    RANK_ZH = {
        "World Rankings": "世界排名",
        "1 Year List for the 2026/2027 Season": "2026/27 赛季单年榜",
        "End of Season Rankings": "赛季末排名",
        "Centuries Count": "单杆破百榜",
        "Players AST": "平均出杆时间榜",
    }
    # 同一榜单有「官方 Official」与「实时 Live」两个版本，按名称归并
    groups = {}
    order = []
    for item in raw_rankings:
        a = item["attributes"]
        if not a.get("published"):
            continue
        name_en = sval(a.get("name"))
        positions = []
        for p in (a.get("positions") or []):
            pl = p.get("player") or {}
            en = player_name_en(pl)
            code = sval(pl.get("country"))
            positions.append({
                "pos": p.get("position"),
                "playerId": p.get("playerID"),
                "name_en": en,
                "name_zh": T.player_zh(en) or en,
                "country": code,
                "country_zh": T.country_code_zh(code),
                "country_en": T.country_code_en(code),
                "photo": f"{IMG}{pl['media']['profile']}"
                         if (pl.get("media") or {}).get("profile") else "",
                "prizeMoney": p.get("prizeMoney"),
                "centuries": p.get("centuriesCount"),
                "ast": p.get("playerAst"),
            })
        positions.sort(key=lambda x: x["pos"] or 9999)
        variant = {
            "id": item["id"],
            "type": sval(a.get("rankingType")),
            "live": bool(a.get("live")),
            "label": "实时" if a.get("live") else "官方",
            "label_en": "Live" if a.get("live") else "Official",
            "updated": sval(a.get("recalculateAfter")),
            "positions": positions,
        }
        if name_en not in groups:
            order.append(name_en)
            groups[name_en] = {
                "name_en": name_en,
                "name_zh": RANK_ZH.get(name_en, name_en),
                "description": sval(a.get("rankingDescription")),
                "variants": [],
            }
        groups[name_en]["variants"].append(variant)

    rankings = []
    for name_en in order:
        g = groups[name_en]
        g["variants"].sort(key=lambda v: not v["live"])  # 实时在前
        g["defaultIndex"] = 0
        rankings.append(g)
    print(f"  排名榜：{len(rankings)} 组（共 "
          f"{sum(len(g['variants']) for g in rankings)} 个版本）")

    # ---------------------------------------------------------- 榜单派生
    centuries.sort(key=lambda c: (-c["value"], c["date"]))
    active = [p for p in players.values() if p["matches"] > 0]

    def top(key, n=20, min_matches=0):
        # 所有榜单均为「数值越高越靠前」，直接降序排序
        pool = [p for p in active if p["matches"] >= min_matches]
        pool.sort(key=lambda p: (p[key], p["wins"]), reverse=True)
        return [{
            "playerId": p["id"], "name_en": p["name_en"],
            "name_zh": p["name_zh"], "country": p["country"],
            "country_zh": p["country_zh"], "photo": p["photo"],
            "value": p[key], "matches": p["matches"],
        } for p in pool[:n]]

    leaderboards = {
        "centuries": top("centuries"),
        "highestBreak": top("highestBreak"),
        "fiftyPlus": top("fiftyPlus"),
        "centuryRate": top("centuryRate", min_matches=1),
        "fiftyRate": top("fiftyRate", min_matches=1),
        "wins": top("wins"),
        "titles": top("titles", n=15, min_matches=1),
    }

    # ---------------------------------------------------------- 历史冠军榜
    # 少数球员只在 matches.json 里出现过，fetch_titles.py 拿不到国家代码，
    # 这里用现役名单兜底补上（否则冠军榜会出现空白的「国家/地区」）。
    country_fb = {}
    for _p in players.values():
        if _p.get("name_en") and _p.get("country"):
            country_fb[_p["name_en"].strip().lower()] = _p["country"]
    title_board = TB.build(country_fb=country_fb)
    tb_meta = title_board.get("meta", {})
    if title_board.get("rows"):
        print(f"  历史冠军榜：{tb_meta.get('rows')} 人上榜，"
              f"排名赛冠军合计 {tb_meta.get('rankingTitles')}")

    # ---------------------------------------------------------- 生涯奖金
    # CueTracker 全时段奖金榜（单次请求拿全量，1623 人），按 slug 精确匹配。
    # 生涯累计值变化慢，只在全量刷新（refresh.sh / fetch_prize_money.py）时更新。
    prize_path = os.path.join(RAW_DIR, "prize_money.json")
    prize_raw = {}
    if os.path.exists(prize_path):
        with open(prize_path, encoding="utf-8") as fh:
            prize_raw = json.load(fh).get("players", {})
        _hits = 0
        for _r in title_board.get("rows", []):
            _pm = prize_raw.get(_r.get("slug"))
            if _pm:
                _r["prize"] = _pm["amount"]
                _r["prizeRank"] = _pm["rank"]
                _hits += 1
        print(f"  生涯奖金：榜单 {len(prize_raw)} 人，冠军榜命中 {_hits} 人")
    else:
        print("  生涯奖金：未找到 data/raw/prize_money.json，跳过"
              "（运行 python3 scripts/fetch_prize_money.py 生成）")

    # 冠军榜已按权威 slug 匹配过，这里复用其结果按姓名反查，避免 slugify 差异
    prize_by_name = {}
    for _r in title_board.get("rows", []):
        if _r.get("prize") is not None and _r.get("name_en"):
            prize_by_name[_r["name_en"].strip().lower()] = _r["prize"]

    # 给每位球员挂上「转职业以来生涯冠军」（来自 CueTracker）
    slug2career = {r["slug"]: r for r in title_board.get("rows", [])}
    career_hits = 0
    prize_hits = 0
    for _p in players.values():
        _slug = T.slugify(_p.get("name_en", ""))
        _c = slug2career.get(_slug)
        if _c:
            _p["career"] = {
                "slug": _slug,
                "ranking": _c["ranking"],
                "nonRanking": _c["nonRanking"],
                "total": _c["total"],
                "crown": _c["crown"],
                "first": _c["first"],
                "last": _c["last"],
                "items": _c["items"],
            }
            career_hits += 1
        # 生涯奖金（按权威 slug 命中，其次按姓名反查），用于球员弹窗
        _pm = prize_raw.get(_slug) or (
            prize_by_name.get(_p.get("name_en", "").strip().lower())
            if _p.get("name_en") else None)
        if _pm:
            _p["prize"] = _pm["amount"]
            _p["prizeRank"] = _pm["rank"]
            if _c:
                _p["career"]["prize"] = _pm["amount"]
                _p["career"]["prizeRank"] = _pm["rank"]
            prize_hits += 1
    print(f"  球员生涯数据命中：{career_hits} 人（含奖金 {prize_hits} 人）")

    # 把「转职业以来生涯冠军」反查挂到排名榜每个位置（用于排名页显示冠军数）
    for _g in rankings:
        for _var in _g["variants"]:
            for _pos in _var["positions"]:
                _cp = players.get(_pos.get("playerId"))
                _c = _cp.get("career") if _cp else None
                if _c:
                    _pos["titlesRank"] = _c["ranking"]
                    _pos["titlesNonRank"] = _c["nonRanking"]
                    _pos["titlesTotal"] = _c["total"]
                else:
                    # CueTracker 无职业冠军记录 = 0 冠（如斯佳辉、周跃龙等新人）
                    _pos["titlesRank"] = 0
                    _pos["titlesNonRank"] = 0
                    _pos["titlesTotal"] = 0
    _titled = sum(1 for _g in rankings for _var in _g["variants"]
                  for _pos in _var["positions"]
                  if _pos["titlesRank"] or _pos["titlesNonRank"])
    print(f"  排名榜位置已挂冠军数：{_titled} 个位置含非零冠军")

    # ---------------------------------------------------------- 汇总指标
    completed = [m for m in matches if m["status"] == "Completed"]
    total_frames = sum(len(m["frames_detail"]) for m in completed)
    finished_events = [t for t in tournaments if t["winner"]]
    china_players = [p for p in active if p["country"] == "CHN"]

    # 正赛按「独立赛事」去重（冠军联赛各阶段算一站）
    main_events = {}
    for t in tournaments:
        if t["isQualifier"]:
            continue
        if t["core"] not in main_events:
            main_events[t["core"]] = t
    main_list = list(main_events.values())
    ranking_events = [t for t in main_list if t["type"] == M.RANKING]
    invitational_events = [t for t in main_list if t["type"] == M.INVITATIONAL]
    season_prize = sum(t["prizeTotal"] or 0 for t in main_list)

    stats = {
        "matchTotal": len(matches),
        "matchCompleted": len(completed),
        "matchUpcoming": len(matches) - len(completed),
        "tournamentTotal": len(tournaments),
        "mainEventTotal": len(main_list),
        "rankingEvents": len(ranking_events),
        "invitationalEvents": len(invitational_events),
        "tripleCrownEvents": len([t for t in main_list if t["tripleCrown"]]),
        "seasonPrize": season_prize,
        "tournamentFinished": len(finished_events),
        "tournamentOngoing": len([t for t in tournaments
                                  if t["status"] == "ongoing"]),
        "playerTotal": len(active),
        "centuryTotal": len(centuries),
        "maxBreak": max([c["value"] for c in centuries] or [0]),
        "frameTotal": total_frames,
        "chinaPlayers": len(china_players),
        "countries": len({p["country"] for p in active if p["country"]}),
        "titleLeaders": tb_meta.get("rows", 0),
        "titleRankingSum": tb_meta.get("rankingTitles", 0),
        "titleAllSum": tb_meta.get("allTitles", 0),
        "titleCrownSum": tb_meta.get("crownTitles", 0),
    }

    # ---------------------------------------------------------- 输出
    payload = {
        "meta": {
            "generatedAt": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
            "season": SEASON_LABEL,
            "seasonId": SEASON_ID,
            "seasonStart": s_start,
            "seasonEnd": s_end,
            "source": "wst.tv",
            "sourceUrl": "https://www.wst.tv/",
        },
        "stats": stats,
        "tournaments": tournaments,
        "matches": sorted(matches, key=lambda m: (m["date"], m["time"])),
        "players": sorted(active, key=lambda p: (-p["wins"], p["name_en"])),
        "allPlayers": sorted(players.values(), key=lambda p: p["name_en"]),
        "rankings": rankings,
        "centuries": centuries,
        "leaderboards": leaderboards,
        "titleBoard": title_board,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))

    # 同时输出一份 JS 赋值版本，便于直接用 file:// 打开页面（绕过 fetch 跨域限制）
    js_path = os.path.join(BASE_DIR, "data", "dashboard.js")
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("window.SNOOKER_DATA=")
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")

    # 刷新 index.html 里静态资源的 ?v= 版本号，避免分享站点/CDN 缓存旧数据
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    idx = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(idx):
        s = open(idx, encoding="utf-8").read()
        # data 脚本
        s2 = re.sub(r'(src="data/(?:h2h|dashboard)\.js)(?:\?v=\d+)?',
                    lambda m: m.group(1) + "?v=" + ts, s)
        # app.js / style.css
        s2 = re.sub(r'((?:src|href)="(?:assets/js/app\.js|assets/css/style\.css))(?:\?v=\d+)?"',
                    lambda m: m.group(1) + "?v=" + ts + "\"", s2)
        if s2 != s:
            open(idx, "w", encoding="utf-8").write(s2)
            print(f"已刷新 index.html 缓存版本号 ?v={ts}")

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print("\n" + "=" * 46)
    print(f"✓ 已生成 {OUT_PATH}  ({size_kb:.0f} KB)")
    print(f"  赛事 {stats['tournamentTotal']} 站（已完赛 "
          f"{stats['tournamentFinished']}）｜比赛 {stats['matchCompleted']}/"
          f"{stats['matchTotal']} 场")
    print(f"  参赛球员 {stats['playerTotal']} 人（来自 "
          f"{stats['countries']} 个国家和地区，其中中国球员 "
          f"{stats['chinaPlayers']} 人）")
    print(f"  单杆破百 {stats['centuryTotal']} 杆｜单杆最高 "
          f"{stats['maxBreak']} 分｜总局数 {stats['frameTotal']}")


if __name__ == "__main__":
    main()
