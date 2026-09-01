#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 wst.tv 官方数据接口抓取斯诺克数据。

数据源（World Snooker Tour 公开 JSON:API）:
  - seasons     : https://seasons.snooker.web.gc.wstservices.co.uk/v2/
  - rankings    : https://rankings.snooker.web.gc.wstservices.co.uk/v2/
  - tournaments : https://tournaments.snooker.web.gc.wstservices.co.uk/v2/
  - players     : https://players.snooker.web.gc.wstservices.co.uk/v2/
  - matches     : https://matches.snooker.web.gc.wstservices.co.uk/v2/

用法:
    python3 fetch_data.py            # 抓取全部
    python3 fetch_data.py --fast      # 跳过 matches 增量（用已有缓存）
"""

import argparse
import concurrent.futures
import http.client
import json
import os
import ssl as _ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wst.tv/",
    "Origin": "https://www.wst.tv",
}

ENDPOINTS = {
    "seasons": "https://seasons.snooker.web.gc.wstservices.co.uk/v2/",
    "rankings": "https://rankings.snooker.web.gc.wstservices.co.uk/v2/",
    "tournaments": "https://tournaments.snooker.web.gc.wstservices.co.uk/v2/",
    "players": "https://players.snooker.web.gc.wstservices.co.uk/v2/",
    "matches": "https://matches.snooker.web.gc.wstservices.co.uk/v2/",
}

# matches 支持 size 参数，用 500 减少请求轮次
PAGE_SIZE = {"matches": 500}


def salvage_partial(raw):
    """服务端截断响应时，尽量从已收到的字节里抢救完整数据。

    返回解析后的 dict；若整体可解析则直接返回，否则用 JSONDecoder.raw_decode
    增量抽取 data 数组里『所有完整对象』（丢弃最后那个被截断的对象）。
    无可抢救内容时返回 None。
    """
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if '"data"' not in text:
        return None
    try:
        dec = json.JSONDecoder()
        i = text.find('"data"')
        j = text.find("[", i)
        objs = []
        k = j + 1
        n = len(text)
        while k < n:
            while k < n and text[k] in " \t\r\n,":
                k += 1
            if k >= n:
                break
            try:
                obj, end = dec.raw_decode(text, k)
                objs.append(obj)
                k = end
            except json.JSONDecodeError:
                break
        return {"data": objs}
    except Exception:  # noqa: BLE001
        return None


_SSL_CTXS = None


def _ssl_contexts():
    """优先用系统默认证书链（开启校验）；若构建失败则退化为不校验。"""
    global _SSL_CTXS
    if _SSL_CTXS is not None:
        return _SSL_CTXS
    verified = None
    try:
        verified = _ssl.create_default_context()
    except Exception:  # noqa: BLE001
        verified = None
    unverified = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
    unverified.check_hostname = False
    unverified.verify_mode = _ssl.CERT_NONE
    _SSL_CTXS = (verified, unverified)
    return _SSL_CTXS


def open_url(url, timeout):
    """打开 URL：默认校验证书；遇到 SSL 证书校验失败（环境/代理偶发）自动降级为不校验，
    确保公开只读 JSON 接口在证书链不稳定时仍能抓取。"""
    verified, unverified = _ssl_contexts()
    last = None
    for idx, ctx in enumerate((verified, unverified)):
        if ctx is None:
            continue
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.URLError as exc:  # urlopen 把 SSL 异常包成 URLError
            reason = getattr(exc, "reason", None)
            if idx == 0 and unverified is not None and isinstance(reason, _ssl.SSLError):
                last = exc
                continue
            raise
        except _ssl.SSLError as exc:  # noqa: BLE001
            if idx == 0 and unverified is not None:
                last = exc
                continue
            raise
    if last is not None:
        raise last
    raise RuntimeError("无法建立 HTTPS 连接")


def get_json(url, retries=4, timeout=60):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with open_url(url, timeout) as resp:
                try:
                    raw = resp.read()
                except http.client.IncompleteRead as exc:  # noqa: BLE001
                    # 服务端多报 Content-Length、实际已发完整 JSON：用已收到的字节恢复
                    raw = exc.partial
            data = salvage_partial(raw)
            if data is None:
                raise RuntimeError("响应不可解析且无可抢救的 data 数组")
            return data
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, TimeoutError, OSError,
                http.client.IncompleteRead, RuntimeError) as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 {url}: {last_err}")


def fetch_collection(name, verbose=True, concurrency=1):
    """分页抓取一个 JSON:API 集合。

    WST 接口特性（2026-09 实测）：
      - 每页硬限 100 条，size= 参数被忽略；
      - meta 时常为 null（totalCount 丢失/为 null），因此优先用 totalCount 算页数，
        缺失时用「指数探测 + 二分」兜底（连续 2 个空页才判定结束，防截断误判）；
      - filter[...] 系列参数行为不稳定，抓全量后在构建层按赛季过滤。

    并发会诱发服务端截断（IncompleteRead），导致某些页丢掉末尾若干对象。
    因此主抓取后追加一轮「缺页补抓」：凡返回条数 < 100 的页（含末页）都顺序
    重抓，直到该页去重新增为 0 或达重试上限，最大化完整度。
    """
    url = ENDPOINTS[name]
    size = PAGE_SIZE.get(name)

    def merge(rows):
        cnt = 0
        for it in rows:
            key = it.get("id")
            if key not in seen:
                seen.add(key)
                items.append(it)
                cnt += 1
        return cnt

    # 种子：若已有缓存文件，加载为初始集合（多轮重跑累积，抗随机截断）
    seed_path = os.path.join(RAW_DIR, f"{name}.json")
    items, seen = [], set()
    if os.path.exists(seed_path):
        try:
            seed = json.load(open(seed_path, encoding="utf-8"))
            items = list(seed)
            seen = {it.get("id") for it in seed}
            if verbose and seed:
                print(f"  [{name}] 种子缓存: {len(items)} 条")
        except Exception:  # noqa: BLE001
            items, seen = [], set()
    first_url = url
    if size and "size=" not in first_url:
        first_url += ("&" if "?" in first_url else "?") + f"size={size}"
    first = get_json(first_url)
    page1 = first.get("data", [])
    meta = first.get("meta") or {}
    total = meta.get("totalCount")
    per_page = len(page1) or 100
    merge(page1)
    if verbose:
        print(f"  [{name}] page 1: +{len(page1)} / 累计 {len(items)}"
              f"{'' if total is None else f' / 共 {total}'}")

    def fetch_page(k):
        # 注意：WST 该接口用点号分页参数 page.number（非 JSON:API 标准的 page[number]），
        # 方括号写法会被忽略、始终返回第 1 页。
        u = url + f"?page.number={k}"
        return get_json(u)

    # ---------- 确定总页数：totalCount 优先，缺失则探测 ----------
    if total:
        last_page = (total + per_page - 1) // per_page
        if verbose:
            print(f"  [{name}] totalCount={total} → {last_page} 页")
    else:
        # 指数探测：2,4,8… 直到连续 2 个空页（防中间页被截断成空而误判结束）
        lo, hi = 1, 2
        empty_run = 0
        while hi <= 200 and empty_run < 2:
            rows = get_json(url + f"?page.number={hi}").get("data", [])
            if rows:
                lo = hi
                merge(rows)
            else:
                empty_run += 1
                if empty_run >= 2:
                    break
            hi *= 2
        # 二分收敛：lo 非空，hi 附近空（或超上限）
        lo_b, hi_b = lo, min(hi, 201)
        while hi_b - lo_b > 1:
            mid = (lo_b + hi_b) // 2
            rows = get_json(url + f"?page.number={mid}").get("data", [])
            if rows:
                lo_b = mid
                merge(rows)
            else:
                hi_b = mid
        last_page = lo_b
        if verbose:
            print(f"  [{name}] 探测完成: 约 {last_page} 页（每页上限 {per_page}）")

    if last_page <= 1:
        if verbose:
            print(f"  [{name}] 完成: 累计 {len(items)} 条（单页集合）")
        return items

    pages = list(range(2, last_page + 1))
    short_pages = []
    if concurrency > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(fetch_page, k): k for k in pages}
            done_cnt = 1
            for fut in concurrent.futures.as_completed(futs):
                k = futs[fut]
                try:
                    payload = fut.result()
                    rows = payload.get("data", [])
                    merge(rows)
                    if len(rows) < 100:  # 短页（含末页）可能被截断，稍后补抓
                        short_pages.append(k)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ⚠ {name} page {k} 抓取失败: {exc}",
                          file=sys.stderr)
                done_cnt += 1
                if verbose and done_cnt % 10 == 0:
                    print(f"  [{name}] 并发进度: 累计 {len(items)}"
                          f"{'' if total is None else f' / 共 {total}'}")
    else:
        for k in pages:
            try:
                payload = fetch_page(k)
                rows = payload.get("data", [])
                merge(rows)
                if len(rows) < 100:
                    short_pages.append(k)
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠ {name} page {k} 抓取失败: {exc}", file=sys.stderr)
            time.sleep(0.35)

    # 缺页补抓：短页多轮合并（顺序）。沙箱代理会随机截断同一页的不同部分，
    # 单次「新增为 0」不能证明页已完整（可能抓到的是上次的子集），
    # 因此连续 2 轮无新增才判定完整，最多 6 轮；末页也可能被截断，同样覆盖。
    if short_pages:
        short_pages = sorted(set(short_pages))
        if verbose:
            print(f"  [{name}] 补抓短页 {len(short_pages)} 个（多轮合并自愈）")
        for k in short_pages:
            empty_streak = 0
            for attempt in range(6):
                try:
                    payload = get_json(url + f"?page.number={k}", retries=4)
                    cnt = merge(payload.get("data", []))
                    if verbose:
                        print(f"    page {k} round{attempt+1}: +{cnt}")
                    if cnt == 0:
                        empty_streak += 1
                        if empty_streak >= 2:
                            break
                    else:
                        empty_streak = 0
                except Exception as exc:  # noqa: BLE001
                    if verbose:
                        print(f"    ⚠ page {k} 补抓失败: {exc}", file=sys.stderr)
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
                time.sleep(0.4)

    if verbose:
        print(f"  [{name}] 完成: 累计 {len(items)}"
              f"{'' if total is None else f' / 共 {total}'}")
    return items


def save(name, items):
    path = os.path.join(RAW_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False)
    size_kb = os.path.getsize(path) / 1024
    print(f"  ✓ 已保存 {path} ({len(items)} 条, {size_kb:.0f} KB)")
    return path


def recover_matches_from(items, seen, baseline_path, verbose=True, delay=0.6):
    """按 ID 定向回补 matches 缺失场次。

    背景：沙箱代理对超大分页（含逐局数据的尾页）会随机截断，即便多轮合并
    也无法保证补齐；WST 提供单资源接口 /v2/{id}（即 matches 对象
    links.self 的路径），可绕过整页分页逐条抓取。

    baseline_path 指向含 match id 的 JSON（raw matches 文件、旧版 dashboard.json
    的 matches 数组等均可），比对当前已抓集合，缺失的按 ID 逐条抓取合并。
    """
    try:
        base = json.load(open(baseline_path, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ 无法读取 baseline {baseline_path}: {exc}", file=sys.stderr)
        return 0
    if isinstance(base, dict):
        base = base.get("matches") or base.get("data") or []
    base_ids = [b.get("id") for b in base if b.get("id")]
    missing = [i for i in base_ids if i not in seen]
    if not missing:
        if verbose:
            print("  [matches] 回补: baseline 全部在位，无需回补")
        return 0
    if verbose:
        print(f"  [matches] 回补: baseline 缺 {len(missing)} 场，按 ID 定向抓取…")
    ok = 0
    for mid in missing:
        try:
            payload = get_json(ENDPOINTS["matches"] + mid, retries=4, timeout=45)
            obj = payload.get("data")
            if not obj or obj.get("id") != mid:
                raise RuntimeError("返回对象与请求 ID 不符")
            if mid not in seen:
                seen.add(mid)
                items.append(obj)
                ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"    ⚠ {mid[:8]} 回补失败: {exc}", file=sys.stderr)
        time.sleep(delay)
    if verbose:
        print(f"  [matches] 回补完成: +{ok} / 缺 {len(missing)}")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="只抓取指定资源，逗号分隔")
    parser.add_argument("--skip", help="跳过指定资源，逗号分隔")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="分页并发数（默认 1，顺序；大集合可用 8 加速）")
    parser.add_argument("--recover-from", metavar="PATH",
                        help="matches 定向回补基准文件（含 match id 的 JSON），"
                             "抓完分页后按 /v2/{id} 逐条补齐缺失场次")
    args = parser.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    only = args.only.split(",") if args.only else None
    skip = args.skip.split(",") if args.skip else []
    concurrency = max(1, args.concurrency)

    targets = [k for k in ENDPOINTS
               if (only is None or k in only) and k not in skip]

    print(f"开始抓取 WST 数据 → {RAW_DIR}")
    results = {}
    for name in targets:
        print(f"\n▶ {name}")
        try:
            items = fetch_collection(name, concurrency=concurrency)
            if name == "matches" and args.recover_from:
                recover_matches_from(
                    items, {it.get("id") for it in items},
                    args.recover_from)
            save(name, items)
            results[name] = len(items)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {name} 抓取失败: {exc}", file=sys.stderr)
            results[name] = None

    print("\n" + "=" * 46)
    for k, v in results.items():
        flag = "✓" if v else "✗"
        print(f"  {flag} {k:<12} {v if v is not None else '失败'}")

    failures = [k for k, v in results.items() if not v]
    if failures:
        print(f"\n以下资源抓取失败: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
