# -*- coding: utf-8 -*-
"""
赛事元数据：类型（排名赛 / 邀请赛 / 资格赛）、三大赛标记、奖金兜底值。

WST 的 tournaments 接口不含赛事类型与奖金字段，类型按世界斯诺克巡回赛
通行分类手工维护；奖金优先取 scripts/fetch_prize.py 从官网抓取的结果，
抓取失败时回退到这里的 MANUAL_PRIZE。

键为规范化核心名（见 translations.tournament_core）。
"""

# ---------------------------------------------------------------- 赛事类型
RANKING = "ranking"          # 排名赛 —— 计入世界排名
INVITATIONAL = "invitational"  # 邀请赛 —— 不计世界排名
QUALIFIER = "qualifier"      # 资格赛 —— 附属轮次，非独立头衔

TOURNAMENT_TYPE = {
    "championship league snooker": RANKING,
    "china open": RANKING,
    "wuhan open": RANKING,
    "british open": RANKING,
    "english open": RANKING,
    "shenzhen open": RANKING,
    "northern ireland open": RANKING,
    "international championship": RANKING,
    "uk championship": RANKING,
    "shoot out": RANKING,
    "scottish open": RANKING,
    "german masters": RANKING,
    "welsh open": RANKING,
    "world grand prix": RANKING,
    "players championship": RANKING,
    "world open": RANKING,
    "tour championship": RANKING,
    "world championship": RANKING,
    # 邀请赛
    "shanghai masters": INVITATIONAL,
    "champion of champions": INVITATIONAL,
    "masters": INVITATIONAL,
}

TYPE_ZH = {
    RANKING: "排名赛",
    INVITATIONAL: "邀请赛",
    QUALIFIER: "资格赛",
}
TYPE_EN = {
    RANKING: "Ranking",
    INVITATIONAL: "Invitational",
    QUALIFIER: "Qualifier",
}

# 三大赛（Triple Crown）：英锦赛、大师赛、世界锦标赛
TRIPLE_CROWN = {"uk championship", "masters", "world championship"}

TRIPLE_CROWN_ZH = "三大赛"
TRIPLE_CROWN_EN = "Triple Crown"

# ---------------------------------------------------------------- 奖金兜底
# 官网页面抓不到时的兜底值（2026/27 赛季）
MANUAL_PRIZE = {
    # 冠军联赛官网首页无奖金表，数据来自赛季官方公布
    "championship league snooker": {"total": 328000, "winner": 33000},
}


def classify(core_name, is_qualifier=False):
    """返回赛事类型。资格赛后缀优先于核心名查表。"""
    if is_qualifier:
        return QUALIFIER
    return TOURNAMENT_TYPE.get(core_name, "")


def is_triple_crown(core_name):
    return core_name in TRIPLE_CROWN
