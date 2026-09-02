#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赛事进行中「快速追更」：只重抓进行中赛事的比赛，秒级完成。

背景：
    WST 的 matches 接口 filter 参数全部不生效，只能全量翻页抓取（8800+ 场，
    89 页），且代理对含逐局数据的尾页会随机截断，需要多轮合并校验 —— 一次
    全量刷新要 10-20 分钟。但赛事进行中真正变化的只有当前赛事那几十场。

做法：
    1. 从 data/dashboard.json 找出「进行中 / 临近开赛」的赛事
    2. 从 data/raw/matches.json 取出这些赛事的全部场次 ID（含未开赛的预排场次）
    3. 用单资源接口 /v2/{id}（matches 对象 links.self 的路径）并发重抓，按 ID 替换
    4. 写回 data/raw/matches.json

之后运行 build_dashboard.py 重建看板即可。

用法：
    python3 scripts/refresh_live_matches.py                 # 默认并发 8
    python3 scripts/refresh_live_matches.py --concurrency 4
    python3 scripts/refresh_live_matches.py --days 7        # 临近开赛口径放宽到 7 天
"""

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from fetch_data import ENDPOINTS, RAW_DIR, get_json  # noqa: E402

DASHBOARD = os.path.join(BASE_DIR, "data", "dashboard.json")
RAW_MATCHES = os.path.join(RAW_DIR, "matches.json")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pick_tournaments(dash, days):
    """挑出需要追更的赛事：进行中，或临近开赛（未来 days 天）/刚结束（过去 2 天）。"""
    today = dt.date.today()
    near = today + dt.timedelta(days=days)
    past = today - dt.timedelta(days=2)
    out = []

    def _date(v):
        if not v:
            return None
        try:
            return dt.date.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    for t in dash.get("tournaments", []):
        if t.get("status") == "ongoing":
            out.append(t)
            continue
        if t.get("status") != "upcoming":
            continue
        sd, ed = _date(t.get("startDate")), _date(t.get("endDate"))
        if (sd and sd <= near) or (ed and ed >= past):
            out.append(t)
    return out


def match_ids_for(raw, tids):
    """从 raw matches 中取出属于这些赛事的全部场次 ID。"""
    ids = []
    for m in raw:
        attrs = m.get("attributes") or {}
        if attrs.get("tournamentID") in tids:
            ids.append(m.get("id"))
    return [i for i in ids if i]


def fetch_one(mid):
    try:
        payload = get_json(ENDPOINTS["matches"] + mid, retries=3, timeout=45)
        obj = payload.get("data")
        if not obj or obj.get("id") != mid:
            raise RuntimeError("返回对象与请求 ID 不符")
        return mid, obj, None
    except Exception as exc:  # noqa: BLE001
        return mid, None, str(exc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=8, help="并发数（默认 8）")
    ap.add_argument("--days", type=int, default=3,
                    help="临近开赛口径：未来 N 天内开赛的赛事也纳入（默认 3）")
    args = ap.parse_args()

    dash = load_json(DASHBOARD)
    tours = pick_tournaments(dash, args.days)
    if not tours:
        print("没有进行中或临近开赛的赛事，无需追更。")
        return 0
    tids = {t.get("id") for t in tours if t.get("id")}
    for t in tours:
        print(f"  · {t.get('name_zh') or ''} {t.get('name_en')} "
              f"({t.get('status')}, 已完赛 {t.get('completedMatches')})")

    raw = load_json(RAW_MATCHES)
    index = {}
    for i, m in enumerate(raw):
        if m.get("id"):
            index[m["id"]] = i
    ids = match_ids_for(raw, tids)
    print(f"  raw matches 共 {len(raw)} 场，命中赛事 {len(ids)} 场，开始定向重抓…")

    ok = fail = 0
    changed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        for mid, obj, err in ex.map(fetch_one, ids):
            if err or obj is None:
                fail += 1
                print(f"    ⚠ {str(mid)[:8]} 失败: {err}", file=sys.stderr)
                continue
            ok += 1
            idx = index.get(mid)
            if idx is None:
                index[mid] = len(raw)
                raw.append(obj)
                changed += 1
            else:
                if raw[idx] != obj:
                    raw[idx] = obj
                    changed += 1

    with open(RAW_MATCHES, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False)
    size_mb = os.path.getsize(RAW_MATCHES) / 1024 / 1024
    print(f"  ✓ 抓取成功 {ok} / 失败 {fail}；内容有更新 {changed} 场")
    print(f"  ✓ 已写回 {RAW_MATCHES}（{len(raw)} 条, {size_mb:.1f} MB）")
    print("  下一步：python3 scripts/build_dashboard.py")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
