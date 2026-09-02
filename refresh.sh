#!/bin/bash
# 一键抓取最新 WST 数据并重建看板
set -e
cd "$(dirname "$0")"
# 可用环境变量 PYTHON 覆盖；默认取 PATH 中的 python3（GitHub Actions / Linux 兼容）
PYTHON="${PYTHON:-python3}"
$PYTHON scripts/fetch_data.py --concurrency 8
# 赛事奖金（来自 WST 官网 informationPage，build 时回退手工兜底）
$PYTHON scripts/fetch_prize.py || echo "⚠ 奖金页抓取失败，将使用手工兜底值"
# 生涯冠军（来自 CueTracker，best-effort：被限流时跳过，保留上次结果）
$PYTHON scripts/fetch_titles.py || echo "⚠ 生涯冠军抓取失败（可能限流），沿用已有 titles.json"
# 生涯奖金榜（来自 CueTracker，一次性全量，不触发限流）
$PYTHON scripts/fetch_prize_money.py || echo "⚠ 生涯奖金榜抓取失败，沿用已有 prize_money.json"
# 交手记录 H2H（来自 CueTracker，best-effort：限流敏感，失败则沿用已有 h2h.json）
$PYTHON scripts/fetch_h2h.py || echo "⚠ 交手记录抓取失败（可能限流），沿用已有 h2h.json"
$PYTHON scripts/build_dashboard.py
echo ""
echo "数据刷新完成。可打开 index.html 查看，或运行："
echo "  python3 -m http.server 8848 --bind 127.0.0.1"
