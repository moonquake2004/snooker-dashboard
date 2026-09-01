#!/bin/bash
# 轻量更新：只刷新「进行中赛事」的比赛结果与赛程进度。
# 与 ./refresh.sh 的区别：不重抓奖金页(fetch_prize) 与生涯冠军(fetch_titles)，
# 也不重抓 rankings / players / seasons —— 这些在赛事进行中基本不变。
# 因此从 ~10 分钟降到约 30 秒，专用于「赛事进行中追更比分」。
set -e
cd "$(dirname "$0")"
# 可用环境变量 PYTHON 覆盖；默认取 PATH 中的 python3（GitHub Actions / Linux 兼容）
PYTHON="${PYTHON:-python3}"
echo "▶ 轻量更新：抓取 matches + tournaments（进行中赛事，分页并发 8 加速）"
$PYTHON scripts/fetch_data.py --only matches,tournaments --concurrency 8
echo "▶ 重建看板数据"
$PYTHON scripts/build_dashboard.py
echo ""
echo "✓ 轻量更新完成。已跳过 奖金/生涯冠军/排名/球员 全量抓取。"
echo "  如需完整刷新（换赛季或修正历史数据），请运行 ./refresh.sh"
