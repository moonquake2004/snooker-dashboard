#!/bin/bash
# 轻量更新：只刷新「进行中赛事」的比赛结果与赛程进度。
# 与 ./refresh.sh 的区别：不做 matches 全量翻页（8800+ 场 / 89 页 / 多轮校验，10-20 分钟），
# 改为 scripts/refresh_live_matches.py 做两件事（约 30 秒）：
#   1) 分页扫描 matches 接口前若干页，发现 WST 新生成的场次（后续轮次对象）
#   2) 按 /v2/{id} 定向重抓进行中赛事的场次，刷新比分与逐局数据
# 第 1 步不能省：只按本地已有 ID 重抓，会永远漏掉新轮次，看板会静默停在上一轮。
# 也不重抓奖金页(fetch_prize)、生涯冠军(fetch_titles)、rankings / players / seasons。
#
# 用法：
#   ./refresh_live.sh           # 快速追更（默认，约 20 秒）
#   ./refresh_live.sh --full    # 连 matches 也全量重抓（换赛季、怀疑历史数据有缺口时用）
set -e
cd "$(dirname "$0")"
# 可用环境变量 PYTHON 覆盖；默认取 PATH 中的 python3（GitHub Actions / Linux 兼容）
PYTHON="${PYTHON:-python3}"

FULL=0
for a in "$@"; do
  [ "$a" = "--full" ] && FULL=1
done

# 基础资源自检：build_dashboard.py 需要 seasons / rankings / players / titles / prize_pages。
# 后两者已入库，前三个在 .gitignore 里不入库 —— 全新环境（如 GitHub Actions 首次运行）
# 必须先补齐，否则 build 会 FileNotFoundError。本地有缓存则整段跳过，零开销。
NEED=""
for f in seasons rankings players; do
  [ -s "data/raw/$f.json" ] || NEED="${NEED:+$NEED,}$f"
done
if [ -n "$NEED" ]; then
  echo "▶ 补齐缺失的基础资源: $NEED"
  $PYTHON scripts/fetch_data.py --only "$NEED" --concurrency 4
fi

# 没有 matches 基线时（本地首次 / CI 无缓存）必须全量，否则定向追更无从下手
if [ ! -s "data/raw/matches.json" ]; then
  echo "  （未找到 matches 基线，本次自动切换为全量抓取）"
  FULL=1
fi

echo "▶ 抓取 tournaments（赛事状态 / 名称 / 日期）"
$PYTHON scripts/fetch_data.py --only tournaments --concurrency 4

if [ "$FULL" = "1" ]; then
  echo "▶ 全量重抓 matches（8800+ 场，较慢，请耐心等待）"
  $PYTHON scripts/fetch_data.py --only matches --concurrency 8
else
  echo "▶ 定向追更：只重抓进行中 / 临近开赛赛事的场次"
  $PYTHON scripts/refresh_live_matches.py --concurrency 8
fi

echo "▶ 重建看板数据"
$PYTHON scripts/build_dashboard.py
echo ""
echo "✓ 轻量更新完成。已跳过 奖金/生涯冠军/排名/球员 全量抓取。"
echo "  如需完整刷新（换赛季或修正历史数据），请运行 ./refresh.sh"
