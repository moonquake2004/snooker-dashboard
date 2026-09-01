#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 data/raw/titles.json（CueTracker 生涯夺冠清单）整理成历史冠军榜。

口径说明：
  排名赛冠军 = CueTracker 分类为 Ranking 的夺冠
  非排名赛冠军 = 全部职业夺冠 − 排名赛夺冠（含邀请赛、联赛、次级排名赛）
  全部冠军   = CueTracker 分类为 professional 的全部夺冠
  三大赛     = 世锦赛 + 英锦赛 + 大师赛（按赛事全名精确匹配，上海大师赛等不计入）
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import translations as T  # noqa: E402

TITLES_PATH = os.path.join(ROOT, "data", "raw", "titles.json")
SLUGS_PATH = os.path.join(ROOT, "data", "raw", "titles_cache", "_slugs.json")

TITLE_RE = re.compile(r"^(\d{4})\s+(.+)$")
CROWN = {"world championship", "uk championship", "masters"}

# 国家英文全称 → 三字母代码（LEGACY 名单里写的是英文全称）
_NAME2CODE = {}
for _c, _n in T.COUNTRY_CODE_EN.items():
    _NAME2CODE[_n.lower()] = _c

# CueTracker 的 gb-* 风格代码 → (三字母代码, 中文, 英文)
_GB = {
    "gb-eng": ("ENG", "英格兰", "England"),
    "gb-sct": ("SCO", "苏格兰", "Scotland"),
    "gb-wls": ("WAL", "威尔士", "Wales"),
    "gb-nir": ("NIR", "北爱尔兰", "Northern Ireland"),
}

# CueTracker 偶尔用两位 ISO 代码 → 三位代码（与 T.COUNTRY_CODES 对齐）
_ISO2 = {
    "cn": "CHN", "au": "AUS", "th": "THA", "hk": "HKG",
    "ir": "IRL", "be": "BEL",
}


def split_title(s):
    """'2024 World Grand Prix' → (2024, 'World Grand Prix')"""
    m = TITLE_RE.match((s or "").strip())
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, (s or "").strip()


def norm_country(v):
    """接受三字母代码（CHN）、gb-* 代码（gb-eng）或英文全称（China），
    返回 (code, zh, en)"""
    v = (v or "").strip()
    if not v:
        return "", "", ""
    if v in _GB:
        return _GB[v]
    if len(v) <= 3 and v.isupper():
        code = _ISO2.get(v.lower(), v)
    else:
        code = _NAME2CODE.get(v.lower(), "")
    if code:
        return code, T.COUNTRY_CODES.get(code, v), T.country_code_en(code)
    return "", v, v


def load_slug_names():
    """_slugs.json 是 候选名 → (slug, 命中方式)，反查成 slug → 展示用英文名"""
    if not os.path.exists(SLUGS_PATH):
        return {}
    with open(SLUGS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for name, item in raw.items():
        if not item or not item[0]:
            continue
        slug, how = item[0], (item[1] or "")
        nm = how[7:] if how.startswith("search:") else name
        out.setdefault(slug, nm)
    return out


def build(titles_path=TITLES_PATH):
    if not os.path.exists(titles_path):
        print("  ! 未找到 titles.json，跳过历史冠军榜")
        return {"meta": {}, "rows": []}

    with open(titles_path, encoding="utf-8") as f:
        data = json.load(f)
    names = load_slug_names()

    rows = []
    for slug, p in data.get("players", {}).items():
        total_raw = p.get("total") or []
        if not total_raw:
            continue
        rank_set = set(p.get("ranking") or [])

        items, years, crown_n, rank_n = [], [], 0, 0
        for raw in total_raw:
            year, ev = split_title(raw)
            is_rank = raw in rank_set
            low = ev.lower().strip()
            is_crown = low in CROWN
            if is_rank:
                rank_n += 1
            if is_crown:
                crown_n += 1
            if year:
                years.append(year)
            items.append({
                "y": year,
                "e": ev,
                "z": T.event_zh(ev),
                "r": 1 if is_rank else 0,
                "c": 1 if is_crown else 0,
            })
        items.sort(key=lambda x: (-(x["y"] or 0), x["e"]))

        name_en = names.get(slug) or slug.replace("-", " ").title()
        code, zh, en = norm_country(p.get("countryCode", ""))
        rows.append({
            "slug": slug,
            "name_en": name_en,
            "name_zh": T.player_zh(name_en) or name_en,
            "country": code,
            "country_zh": zh,
            "country_en": en,
            "ranking": rank_n,
            "nonRanking": len(total_raw) - rank_n,
            "total": len(total_raw),
            "crown": crown_n,
            "first": min(years) if years else None,
            "last": max(years) if years else None,
            "items": items,
        })

    rows.sort(key=lambda r: (-r["ranking"], -r["total"], r["last"] or 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    meta = dict(data.get("meta", {}))
    meta["rows"] = len(rows)
    meta["rankingTitles"] = sum(r["ranking"] for r in rows)
    meta["allTitles"] = sum(r["total"] for r in rows)
    meta["crownTitles"] = sum(r["crown"] for r in rows)
    return {"meta": meta, "rows": rows}


if __name__ == "__main__":
    b = build()
    print(f"上榜 {b['meta'].get('rows', 0)} 人｜排名赛冠军合计 "
          f"{b['meta'].get('rankingTitles', 0)}｜全部冠军合计 {b['meta'].get('allTitles', 0)}")
    print(f"{'#':>3} {'球员':<22} {'排名赛':>5} {'非排名':>6} {'全部':>5} {'三大赛':>6}  首冠/末冠")
    for r in b["rows"][:25]:
        print(f"{r['rank']:>3} {r['name_zh']:<10}({r['name_en']:<22}) "
              f"{r['ranking']:>5} {r['nonRanking']:>6} {r['total']:>5} {r['crown']:>6}  "
              f"{r['first']}/{r['last']}")
