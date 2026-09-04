#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赛事进行中「快速追更」：只重抓进行中赛事的比赛，秒级完成。

背景：
    WST 的 matches 接口 filter 参数全部不生效，只能全量翻页抓取（8800+ 场，
    89 页），且代理对含逐局数据的尾页会随机截断，需要多轮合并校验 —— 一次
    全量刷新要 10-20 分钟。但赛事进行中真正变化的只有当前赛事那几十场。

做法：
    1. 从 data/dashboard.json 找出「进行中 / 临近开赛」的赛事
    2. 【新场次发现】用 page.number 分页扫描 matches 接口前若干页（接口按
       startDateTime 倒序，进行中赛事的场次必然排在前面），把属于这些赛事的
       场次全部并入 raw
    3. 从 data/raw/matches.json 取出这些赛事的全部场次 ID（含上一步新发现的）
    4. 用单资源接口 /v2/{id}（matches 对象 links.self 的路径）并发重抓，按 ID 替换
    5. 写回 data/raw/matches.json

第 2 步不可省略：WST 会随赛程推进「新生成」后续轮次的场次对象（第四轮、1/4
决赛等），这些新场次的 ID 根本不在本地 raw 里，只做第 3 步的定向重抓会永远
漏掉它们，导致看板停在上一轮。2026-09-04 英国公开赛就踩过这个坑：本地停在
第三轮，官网已经在打 1/4 决赛，漏了 20 场。

⚠ 分页参数必须用点号 page.number=N；方括号 page[number]=N 会被接口忽略、
永远返回第 1 页（这个坑 fetch_data.py 里有注释，别再踩）。

之后运行 build_dashboard.py 重建看板即可。

用法：
    python3 scripts/refresh_live_matches.py                 # 默认并发 8
    python3 scripts/refresh_live_matches.py --concurrency 4
    python3 scripts/refresh_live_matches.py --days 7        # 临近开赛口径放宽到 7 天
    python3 scripts/refresh_live_matches.py --discover-pages 12
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


def _start_date(m):
    """取场次开赛日期字符串（YYYY-MM-DD），取不到返回空串。"""
    v = (m.get("attributes") or {}).get("startDateTime")
    return str(v)[:10] if v else ""


def discover_new_matches(tids, raw, index, max_pages=10, verbose=True):
    """分页扫描发现新场次（含 WST 后续轮次新生成的对象）。

    matches 集合接口按 startDateTime 倒序返回，因此进行中赛事的场次必然排在
    最前面几页。逐页扫描，把属于 tids 的场次并入 raw：
      - 新 ID 追加（这就是「新场次发现」）
      - 已有 ID 用线上数据替换（顺带刷新存量比分/状态）

    早停条件：某页内所有场次的开赛日期都早于 cutoff（目标赛事最早开赛日
    前推 60 天），说明已经扫过目标赛事所在的时间段，无需再往后翻。
    """
    # 用 raw 里已有场次推算 cutoff，避免漏掉跨月长赛程
    known = [_start_date(m) for m in raw
             if (m.get("attributes") or {}).get("tournamentID") in tids]
    known = sorted(d for d in known if d)
    cutoff = known[0] if known else ""
    if cutoff:
        try:
            cutoff = str(dt.date.fromisoformat(cutoff) - dt.timedelta(days=60))
        except ValueError:
            cutoff = ""

    added = updated = 0
    scanned = 0
    for page in range(1, max_pages + 1):
        try:
            payload = get_json(ENDPOINTS["matches"] + f"?page.number={page}",
                               retries=3, timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"    ⚠ 分页扫描 page {page} 失败: {exc}", file=sys.stderr)
            break
        rows = payload.get("data") or []
        if not rows:
            break
        scanned += len(rows)
        page_dates = []
        for obj in rows:
            attrs = obj.get("attributes") or {}
            page_dates.append(str(attrs.get("startDateTime") or "")[:10])
            if attrs.get("tournamentID") not in tids:
                continue
            mid = obj.get("id")
            if not mid:
                continue
            idx = index.get(mid)
            if idx is None:
                index[mid] = len(raw)
                raw.append(obj)
                added += 1
            elif raw[idx] != obj:
                raw[idx] = obj
                updated += 1
        # 早停：整页都早于 cutoff（未来场次日期大，不会误停）
        latest = max((d for d in page_dates if d), default="")
        if cutoff and latest and latest < cutoff:
            if verbose:
                print(f"    分页扫描至 page {page}（最新日期 {latest} < cutoff "
                      f"{cutoff}），停止")
            break

    if verbose:
        print(f"  ✓ 分页扫描 {page} 页 / {scanned} 场：新发现 {added} 场，"
              f"刷新存量 {updated} 场")
    return added, updated


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
    ap.add_argument("--discover-pages", type=int, default=10,
                    help="新场次发现：最多扫描 matches 接口前 N 页（默认 10）")
    ap.add_argument("--no-discover", action="store_true",
                    help="跳过新场次发现（仅定向重抓，会漏掉新生成的轮次场次）")
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
    before = len(match_ids_for(raw, tids))
    print(f"  raw matches 共 {len(raw)} 场，命中赛事 {before} 场")

    if not args.no_discover:
        print(f"  ▸ 分页扫描发现新场次（最多 {args.discover_pages} 页）…")
        discover_new_matches(tids, raw, index, args.discover_pages)

    # 重新计算：含上一步新发现的场次
    ids = match_ids_for(raw, tids)
    print(f"  ▸ 定向重抓 {len(ids)} 场（新发现 {max(0, len(ids) - before)} 场）…")

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
