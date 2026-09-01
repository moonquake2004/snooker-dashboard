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

    concurrency>1 时，第一页顺序抓取以确定总量，其余页用线程池并发抓取，
    可把 8833 场这种大集合的抓取从 ~8 分钟降到 ~1 分钟（WST 接口每页硬限 100、
    且 filter 不生效，只能整集合拉回）。
    """
    url = ENDPOINTS[name]
    size = PAGE_SIZE.get(name)
    # 第一页（顺序，拿到 total 与每页实际条数）
    first_url = url
    if size and "size=" not in first_url:
        first_url += ("&" if "?" in first_url else "?") + f"size={size}"
    first = get_json(first_url)
    page1 = first.get("data", [])
    meta = first.get("meta") or {}
    total = meta.get("totalCount")
    per_page = len(page1) or 1
    total_pages = ((total + per_page - 1) // per_page) if total else 1
    items = list(page1)
    seen = {it.get("id") for it in page1}
    if verbose:
        print(f"  [{name}] page 1: +{len(page1)} / 累计 {len(items)}"
              f"{'' if total is None else f' / 共 {total}'}")

    if total_pages <= 1:
        return items

    def fetch_page(k):
        # 注意：WST 该接口用点号分页参数 page.number（非 JSON:API 标准的 page[number]），
        # 方括号写法会被忽略、始终返回第 1 页。
        sep = "&" if "?" in url else "?"
        u = url + sep + f"page.number={k}"
        return get_json(u)

    pages = list(range(2, total_pages + 1))
    if concurrency > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(fetch_page, k): k for k in pages}
            done_cnt = 1
            for fut in concurrent.futures.as_completed(futs):
                try:
                    payload = fut.result()
                    for it in payload.get("data", []):
                        key = it.get("id")
                        if key not in seen:
                            seen.add(key)
                            items.append(it)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ⚠ {name} page {futs[fut]} 抓取失败: {exc}",
                          file=sys.stderr)
                done_cnt += 1
                if verbose and done_cnt % 10 == 0:
                    print(f"  [{name}] 并发进度: 累计 {len(items)} / 共 {total}")
    else:
        for k in pages:
            try:
                payload = fetch_page(k)
                for it in payload.get("data", []):
                    key = it.get("id")
                    if key not in seen:
                        seen.add(key)
                        items.append(it)
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠ {name} page {k} 抓取失败: {exc}", file=sys.stderr)
            time.sleep(0.35)

    if verbose:
        print(f"  [{name}] 完成: 累计 {len(items)} / 共 {total}")
    return items


def save(name, items):
    path = os.path.join(RAW_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False)
    size_kb = os.path.getsize(path) / 1024
    print(f"  ✓ 已保存 {path} ({len(items)} 条, {size_kb:.0f} KB)")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="只抓取指定资源，逗号分隔")
    parser.add_argument("--skip", help="跳过指定资源，逗号分隔")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="分页并发数（默认 1，顺序；大集合可用 8 加速）")
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
