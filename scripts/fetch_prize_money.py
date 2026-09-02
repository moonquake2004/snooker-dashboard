#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 CueTracker「全时段生涯奖金榜」→ data/raw/prize_money.json。

数据源（服务端渲染，无需登录）：
  https://cuetracker.net/statistics/prize-money/won/all-time

这个页面一次返回全部球员（1600+ 人）的生涯总奖金（单位 GBP），**无分页**，
因此只需 1 个 HTTP 请求即可拿全量 —— 与 H2H 那种上千次请求、动辄几小时且会被
429 限流的抓取完全不同。

输出结构：
  {
    "meta": {"source": ..., "url": ..., "fetched": ..., "count": N, "currency": "GBP"},
    "players": {
      "<cuetracker-slug>": {"name": "Ronnie O'Sullivan", "amount": 15253217, "rank": 1},
      ...
    }
  }

slug 与 data/raw/titles.json / titleBoard 使用的 CueTracker slug 完全一致，
下游按 slug 精确匹配即可，无需做姓名模糊匹配。

用法：
    python3 scripts/fetch_prize_money.py
    python3 scripts/fetch_prize_money.py --top 20     # 打印前 20 名
"""

import argparse
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, "data", "raw", "prize_money.json")

URL = "https://cuetracker.net/statistics/prize-money/won/all-time"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")


def get(url, retries=3, timeout=60):
    """带 gzip 的 GET。

    必须显式要 gzip：这个页面未压缩时约 600KB+，沙箱代理对无 Content-Length 的
    大响应会中途截断（http.client.IncompleteRead）；开启 gzip 后降到几十 KB 即稳定。
    """
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip",
    }
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < retries:
                time.sleep(2 * (i + 1))
    raise RuntimeError(f"抓取失败 {url}: {last}")


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def parse(html):
    """解析奖金榜表格。

    行结构（实测）：
      <tr><td></td>
          <td class="text-left"><img class="flag flag-england" ...>
              <a href="https://cuetracker.net/players/ronnie-osullivan">Ronnie O'Sullivan</a></td>
          <td class="text-left">15,253,217</td></tr>
    """
    tables = re.findall(r"<table[^>]*>.*?</table>", html, re.S)
    if not tables:
        raise RuntimeError("页面中没有找到表格，可能是结构变更或被限流")

    players = {}
    for tb in tables:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S):
            m = re.search(r'href="https?://(?:www\.)?cuetracker\.net/players/([^"/?#]+)"', row)
            if not m:
                continue
            slug = m.group(1)
            name_m = re.search(r">([^<>]+)</a\s*>", row)
            tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
            amt = None
            for td in reversed(tds):
                txt = clean(td)
                if re.fullmatch(r"[\d,]+", txt):
                    amt = int(txt.replace(",", ""))
                    break
            if amt is None:
                continue
            players[slug] = {
                "name": clean(name_m.group(1)) if name_m else slug,
                "amount": amt,
            }
        if players:
            break

    # 按金额降序补 rank
    for i, slug in enumerate(sorted(players, key=lambda s: -players[s]["amount"]), 1):
        players[slug]["rank"] = i
    return players


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10, help="打印前 N 名（默认 10）")
    ap.add_argument("--out", default=OUT, help="输出路径")
    args = ap.parse_args()

    print(f"抓取 {URL} …")
    html = get(URL)
    print(f"  响应 {len(html) / 1024:.0f} KB")

    players = parse(html)
    if not players:
        print("!! 解析结果为空，放弃写入", file=sys.stderr)
        return 1

    payload = {
        "meta": {
            "source": "cuetracker.net",
            "url": URL,
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(players),
            "currency": "GBP",
            "note": "Career prize money (all-time)，单位英镑",
        },
        "players": players,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    size_kb = os.path.getsize(args.out) / 1024
    print(f"  ✓ 已保存 {args.out}（{len(players)} 人, {size_kb:.0f} KB）")
    print(f"\n生涯奖金 Top {args.top}（GBP）：")
    for slug in sorted(players, key=lambda s: players[s]["rank"])[:args.top]:
        p = players[slug]
        print(f"  {p['rank']:>3}. {p['name']:<24s} £{p['amount']:>12,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
