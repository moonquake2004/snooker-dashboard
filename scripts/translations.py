# -*- coding: utf-8 -*-
"""
中英双语映射表：球员 / 赛事 / 城市 / 国家 / 轮次 / 状态。

球员译名以中文媒体通行译法为准（中国球员取官方汉字名）；
赛事采用「剥离赞助商 → 匹配核心名 → 拼装后缀」的方式生成，
避免逐条硬编码 39 站全名。
"""

import re

# ---------------------------------------------------------------- 球员
PLAYERS = {
    # 中国
    "Bai Yulu": "白雨露", "Chang Bingyu": "常冰玉", "Chen Qien": "陈麒恩",
    "Deng Haohui": "邓壕辉", "Ding Junhui": "丁俊晖", "Fan Zhengyi": "范争一",
    "Gao Yang": "高阳", "Gong Chenzhi": "巩晨智", "He Guoqiang": "贺国强",
    "Huang Jiahao": "黄佳浩", "Jiang Jun": "江俊", "Lan Yuhao": "蓝裕豪",
    "Lei Peifan": "雷佩凡", "Linhao Liu": "刘林浩", "Liu Hongyu": "刘宏宇",
    "Liu Wenwei": "刘文炜", "Liu Yang": "刘杨", "Long Zehuang": "龙泽煌",
    "Luo Zetao": "罗泽涛", "Lyu Haotian": "吕昊天", "Pang Junxu": "庞俊旭",
    "Si Jiahui": "斯佳辉", "Wang Xinbo": "王信伯", "Wu Shengguang": "吴圣光",
    "Wu Yize": "吴宜泽", "Xiao Guodong": "肖国栋", "Xu Si": "徐思",
    "Xu Yichen": "许医尘", "Yao Pengcheng": "姚朋成", "Yuan Sijun": "袁思俊",
    "Zhang Anda": "张安达", "Zhao Hanyang": "赵翰洋", "Zhao Xintong": "赵心童",
    "Zhen Guan": "管震", "Zhou Yuelong": "周跃龙",
    # 中国香港
    "Cheung Ka Wai": "张家玮", "Marco Fu": "傅家俊", "Onyee Ng": "吴安仪",
    # 英格兰
    "Alfie Burden": "阿尔菲·伯登", "Ali Carter": "阿里·卡特",
    "Andrew Higginson": "安德鲁·希金森", "Ashley Carty": "阿什利·卡蒂",
    "Ashley Hugill": "阿什利·休吉尔", "Barry Hawkins": "巴里·霍金斯",
    "Ben Woollaston": "本·沃拉斯顿", "Chris Wakelin": "克里斯·韦克林",
    "Connor Benzey": "康纳·本泽", "Craig Steadman": "克雷格·斯特德曼",
    "David Gilbert": "大卫·吉尔伯特", "David Grace": "大卫·格雷斯",
    "David Lilley": "大卫·利里", "Elliot Slessor": "埃利奥特·斯莱瑟",
    "Gary Wilson": "加里·威尔逊", "Hammad Miah": "哈马德·米亚",
    "Ian Burns": "伊恩·伯恩斯", "Jack Lisowski": "杰克·利索夫斯基",
    "Jimmy Robertson": "吉米·罗伯逊", "Jimmy White": "吉米·怀特",
    "Joe O'Connor": "乔·奥康纳", "Judd Trump": "贾德·特鲁姆普",
    "Kyren Wilson": "凯伦·威尔逊", "Liam Highfield": "利亚姆·海菲尔德",
    "Liam Pullen": "利亚姆·普伦", "Louis Heathcote": "路易斯·希思科特",
    "Mark Selby": "马克·塞尔比", "Martin O'Donnell": "马丁·奥唐纳",
    "Matthew Selt": "马修·塞尔特", "Michael Holt": "迈克尔·霍尔特",
    "Mitchell Mann": "米切尔·曼恩", "Oliver Brown": "奥利弗·布朗",
    "Oliver Lines": "奥利弗·莱恩斯", "Oliver Sykes": "奥利弗·赛克斯",
    "Paul Norris": "保罗·诺里斯", "Phil O'Kane": "菲尔·奥凯恩",
    "Reanne Evans": "瑞安·埃文斯", "Ricky Walden": "里奇·沃顿",
    "Robbie Williams": "罗比·威廉姆斯", "Ronnie O'Sullivan": "罗尼·奥沙利文",
    "Sam Craigie": "萨姆·克雷吉", "Sean O'Sullivan": "肖恩·奥沙利文",
    "Shaun Murphy": "肖恩·墨菲", "Stan Moody": "斯坦·穆迪",
    "Steven Hallworth": "史蒂文·霍尔沃斯", "Stuart Bingham": "斯图尔特·宾汉姆",
    "Stuart Carrington": "斯图尔特·卡林顿", "Tom Ford": "汤姆·福德",
    "Zak Surety": "扎克·苏瑞特",
    # 威尔士
    "Daniel Wells": "丹尼尔·威尔斯", "Dylan Emery": "迪伦·埃默里",
    "Jackson Page": "杰克逊·佩奇", "Jak Jones": "杰克·琼斯",
    "Jamie Clarke": "杰米·克拉克", "Jamie Jones": "杰米·琼斯",
    "Liam Davies": "利亚姆·戴维斯", "Mark Williams": "马克·威廉姆斯",
    "Matthew Stevens": "马修·史蒂文斯", "Ryan Day": "瑞恩·戴",
    # 苏格兰
    "Anthony McGill": "安东尼·麦克吉尔", "John Higgins": "约翰·希金斯",
    "Liam Graham": "利亚姆·格雷厄姆", "Ross Muir": "罗斯·缪尔",
    "Scott Donaldson": "斯科特·唐纳森", "Stephen Maguire": "斯蒂芬·马奎尔",
    # 北爱尔兰
    "Fergal Quinn": "弗加尔·奎因", "Jordan Brown": "乔丹·布朗",
    "Mark Allen": "马克·艾伦",
    # 其他
    "Neil Robertson": "尼尔·罗伯逊",
    "Florian Nuessle": "弗洛里安·纽斯利",
    "Ben Mertens": "本·默藤斯", "Julien Leclercq": "朱利安·莱克勒克",
    "Luca Brecel": "卢卡·布雷切尔",
    "Igor Figueiredo": "伊戈尔·菲格雷多",
    "Sahil Nayyar": "萨希尔·纳亚尔",
    "Alexander Ursenbacher": "亚历山大·乌森巴赫",
    "Mahmoud El Hareedy": "马哈茂德·哈里迪",
    "Aaron Hill": "阿伦·希尔", "Leone Crowley": "利昂·克劳利",
    "Hossein Vafaei": "侯赛因·瓦菲",
    "Artemijs Zizins": "阿尔乔姆·齐津斯",
    "Antoni Kowalski": "安东尼·科瓦尔斯基",
    "Mateusz Baranowski": "马特乌什·巴拉诺夫斯基",
    "Michal Szubarczyk": "米哈尔·苏巴尔奇克",
    "Ishpreet Singh Chadha": "伊什普里特·辛格·查达",
    "Chatchapong Nasa": "查查蓬·纳萨", "Noppon Saengkham": "诺蓬·桑坎姆",
    "Panchaya Channoi": "潘查亚·查诺伊",
    "Thanawat Tirapongpaiboon": "塔纳瓦·提拉蓬派布",
    "Thepchaiya Un-Nooh": "塔猜亚·乌诺",
    "Anton Kazakov": "安东·卡扎科夫", "Iulian Boiko": "尤利安·博伊科",
    "Michael Larkov": "迈克尔·拉尔科夫",
}

# 未出现在 players 主名单中的业余 / 外卡 / 老将球员（从对阵数据中补齐）
PLAYERS_EXTRA = {
    "Robert Milkins": "罗伯特·米尔金斯", "Mark Joyce": "马克·乔伊斯",
    "Allan Taylor": "阿伦·泰勒", "Duane Jones": "杜安·琼斯",
    "Dean Young": "迪恩·扬", "Peter Lines": "彼得·莱恩斯",
    "Daniel Womersley": "丹尼尔·沃莫斯利", "Haydon Pinhey": "海登·平海",
    "Jamie O'Neill": "杰米·奥尼尔", "Brian Ochoiski": "布莱恩·奥乔伊斯基",
    "Vladislav Gradinari": "弗拉迪斯拉夫·格拉迪纳里",
    "Ryan Thomerson": "瑞安·托默森", "Joshua Thomond": "约书亚·托蒙德",
    "Kaylan Patel": "凯兰·帕特尔", "Luke Pinches": "卢克·平奇斯",
    "Simon Blackwell": "西蒙·布莱克威尔", "Sean Maddocks": "肖恩·马多克斯",
    "Jeffrey Cundy": "杰弗里·坎迪", "Ian Martin": "伊恩·马丁",
    "George Pragnell": "乔治·普拉格内尔", "Dylan Smith": "迪伦·史密斯",
    "Jack Bradford": "杰克·布拉德福德", "Alfie Davies": "阿尔菲·戴维斯",
    "Patrick Whelan": "帕特里克·惠兰", "Nattanapong Chaikul": "纳塔纳蓬·猜古",
    # 以下姓名在数据中被写成了「名+姓」的倒序，中文取正序
    "Hewen Tang": "唐和文", "Xinzhong Wang": "王信仲",
    "Dongcheng Yao": "姚东成", "Jiarui Xu": "徐嘉瑞", "Ruifu Chen": "陈瑞福",
    "Yichen Zhou": "周奕辰", "Yuhang Wang": "王宇航", "Zhang Yang": "张洋",
    "Sunny Akani": "阿卡尼·颂瑟沙瓦", "Akani Songsermsawad": "阿卡尼·颂瑟沙瓦",
    "Liang Xiaolong": "梁小龙", "Luo Honghao": "罗弘昊",
    "Wang Yuchen": "王雨晨", "Ng On Yee": "吴安仪",
    "Soheil Vahedi": "索海尔·瓦赫迪", "Muhammad Asif": "穆罕默德·阿西夫",
    "Kreishh Gurbaxani": "克里什·古尔巴克斯尼",
}

# 退役/历史名宿（CueTracker 生涯榜上出现、但不在现役 WST 名单中的球员）
# 用于历史冠军榜的中文名回退
PLAYERS_LEGACY = {
    "Stephen Hendry": "斯蒂芬·亨得利",
    "Steve Davis": "史蒂夫·戴维斯",
    "John Parrott": "约翰·帕洛特",
    "Peter Ebdon": "彼得·艾伯顿",
    "Ken Doherty": "肯·达赫迪",
    "Ray Reardon": "雷·里尔顿",
    "Stephen Lee": "斯蒂芬·李",
    "James Wattana": "詹姆斯·瓦塔纳",
    "Paul Hunter": "保罗·亨特",
    "Cliff Thorburn": "克里夫·桑本",
    "Dennis Taylor": "丹尼斯·泰勒",
    "Doug Mountjoy": "道格·芒乔伊",
    "Joe Perry": "乔·佩里",
    "Alan McManus": "阿兰·麦克马努斯",
    "Dominic Dale": "多米尼克·戴尔",
    "Tony Knowles": "托尼·诺尔斯",
    "Michael White": "迈克尔·怀特",
    "Graeme Dott": "格雷姆·多特",
    "Alex Higgins": "亚历克斯·希金斯",
    "John Spencer": "约翰·斯宾塞",
    "Terry Griffiths": "特里·格里菲斯",
    "Tony Meo": "托尼·梅奥",
    "Willie Thorne": "威利·索恩",
    "Nigel Bond": "奈杰尔·邦德",
    "Mike Hallett": "迈克·哈利特",
    "Neal Foulds": "尼尔·福尔兹",
    "Joe Johnson": "乔·约翰逊",
    "Martin Gould": "马丁·古尔德",
    "Anthony Hamilton": "安东尼·汉密尔顿",
    "David Gray": "大卫·格雷",
    "Silvino Francisco": "西尔维诺·弗朗西斯科",
    "Dave Harold": "戴夫·哈罗德",
    "Liang Wenbo": "梁文博",
    "Yan Bingtao": "颜丙涛",
    "Bob Chaperon": "鲍勃·查普伦",
    "Fergal O'Brien": "费格尔·奥布莱恩",
    "Mark King": "马克·金",
    "Michael Georgiou": "迈克尔·乔治乌",
    "Joe Davis": "乔·戴维斯",
    "Eddie Charlton": "埃迪·查尔顿",
    "Fred Davis": "弗雷德·戴维斯",
    "John Pulman": "约翰·普尔曼",
    "Darren Morgan": "达伦·摩根",
    "Mark Davis": "马克·戴维斯",
    "Joe Swail": "乔·斯维尔",
    "Harry Stokes": "哈里·斯托克斯",
    "John Virgo": "约翰·维果",
    "Perrie Mans": "佩里·曼斯",
    "Alec Brown": "亚历克·布朗",
    "Graham Miles": "格雷厄姆·迈尔斯",
    "Murdo MacLeod": "默多·麦克劳德",
    "Jackie Rea": "杰基·雷亚",
    "Patsy Fagan": "帕齐·费根",
    "Eddie Sinclair": "埃迪·辛克莱",
    "Warren King": "沃伦·金",
    "John Campbell": "约翰·坎贝尔",
    "Tony Drago": "托尼·德拉戈",
    "Jamie Cope": "杰米·科普",
    "Tian Pengfei": "田鹏飞",
    "Kurt Maflin": "库尔特·马夫林",
    "Marcus Campbell": "马库斯·坎贝尔",
    "Rod Lawler": "罗德·劳勒",
    "Rory McLeod": "罗里·麦克劳德",
    "Horace Lindrum": "贺拉斯·林德鲁姆",
    "Dave Martin": "戴夫·马丁",
    "Rex Williams": "雷克斯·威廉姆斯",
    "Kirk Stevens": "柯克·史蒂文斯",
    "Jimmy van Rensberg": "吉米·范伦斯堡",
    "Jon Wright": "乔恩·赖特",
    "Francois Ellis": "弗朗索瓦·埃利斯",
    "Steve Ventham": "史蒂夫·文瑟姆",
    "David Taylor": "大卫·泰勒",
    "Alain Robidoux": "阿兰·罗比杜",
    "Paddy Browne": "帕迪·布朗",
    "Jack McLaughlin": "杰克·麦克劳克林",
    "Troy Shaw": "特洛伊·肖",
    "Andy Hicks": "安迪·希克斯",
    "Chris Norbury": "克里斯·诺伯里",
    "Barry Pinches": "巴里·平奇斯",
    "Ju Reti": "居热提",
}

# 外卡占位名
WILDCARD_RE = re.compile(r"^China Wildcard\s*#?(\d+)$", re.I)

# ---------------------------------------------------------------- 赛事
# 赞助商前缀（按长度降序匹配，先剥长后剥短）
SPONSORS = [
    "Johnstone's Paint", "MachineSeeker", "BetVictor", "Riyadh Season",
    "Saudi Arabia", "Duelbits", "Unibet", "Cazoo", "TAOM", "MrQ", "Halo",
]

# 核心赛事名中英对照（已剥离赞助商与年份后的 key）
EVENTS = {
    "china open": "中国公开赛",
    "wuhan open": "武汉公开赛",
    "shenzhen open": "深圳公开赛",
    "british open": "英国公开赛",
    "english open": "英格兰公开赛",
    "northern ireland open": "北爱尔兰公开赛",
    "scottish open": "苏格兰公开赛",
    "welsh open": "威尔士公开赛",
    "world open": "世界公开赛",
    "shanghai masters": "上海大师赛",
    "masters": "大师赛",
    "champion of champions": "冠中冠",
    "championship league snooker": "冠军联赛",
    "international championship": "国际锦标赛",
    "uk championship": "英锦赛",
    "german masters": "德国大师赛",
    "shoot out": "单局限时赛",
    "world grand prix": "世界大奖赛",
    "players championship": "球员锦标赛",
    "tour championship": "巡回锦标赛",
    "world championship": "世界锦标赛",
    "xi'an grand prix": "西安大奖赛",
    "saudi arabia snooker masters": "沙特阿拉伯大师赛",
    "riyadh season championship": "利雅得赛季锦标赛",
    "world mixed doubles": "世界混双赛",
}

# ---------------------------------------------------------------- 历史赛事
# CueTracker 的赛事名不带赞助商（如 "2004 Grand Prix"），单独建表。
# 覆盖 1970 年代至今的主要排名赛 / 邀请赛 / 次级排名赛。
HISTORIC_EVENTS = {
    # --- 排名赛（已停办或改名） ---
    "grand prix": "大奖赛", "lg cup": "LG杯", "classic": "经典赛",
    "dubai classic": "迪拜经典赛", "thailand masters": "泰国大师赛",
    "asian classic": "亚洲经典赛", "irish masters": "爱尔兰大师赛",
    "european open": "欧洲公开赛", "german open": "德国公开赛",
    "malta cup": "马耳他杯", "malta grand prix": "马耳他大奖赛",
    "international open": "国际公开赛",
    "professional players tournament": "职业球员锦标赛",
    "rothmans grand prix": "乐富门大奖赛", "matchroom trophy": "Matchroom 奖杯赛",
    "kent cup": "肯特杯", "strachan open": "斯特拉坎公开赛",
    "hong kong open": "香港公开赛", "canadian masters": "加拿大大师赛",
    "australian masters": "澳大利亚大师赛", "malaysian masters": "马来西亚大师赛",
    "dubai masters": "迪拜大师赛", "northern ireland trophy": "北爱尔兰杯",
    "australian goldfields open": "澳大利亚金矿公开赛",
    "wuxi classic": "无锡精英赛", "riga masters": "里加大师赛",
    "paul hunter classic": "保罗·亨特经典赛", "indian open": "印度公开赛",
    "gibraltar open": "直布罗陀公开赛", "brazilian masters": "巴西大师赛",
    "zhengzhou open": "郑州公开赛", "haining open": "海宁公开赛",
    "zhangjiagang open": "张家港公开赛", "yixing open": "宜兴公开赛",
    "xuzhou open": "徐州公开赛", "antwerp open": "安特卫普公开赛",
    "bulgarian open": "保加利亚公开赛", "polish masters": "波兰大师赛",
    "romanian masters": "罗马尼亚大师赛", "gdynia open": "格丁尼亚公开赛",
    "lisbon open": "里斯本公开赛", "ruhr open": "鲁尔公开赛",
    "rotterdam open": "鹿特丹公开赛", "irish open": "爱尔兰公开赛",
    "kay suzanne memorial cup": "Kay Suzanne 纪念杯",
    "alex higgins international trophy": "亚历克斯·希金斯国际杯",
    "bluebell wood open": "蓝铃木公开赛", "ffb snooker open": "FFB 斯诺克公开赛",
    "players tour championship": "球员巡回锦标赛",
    # --- 邀请赛 / 非排名赛 ---
    "champions cup": "冠军杯", "premier league": "超级联赛",
    "european league": "欧洲联赛", "matchroom league": "Matchroom 联赛",
    "charity challenge": "慈善挑战赛", "extra challenge": "额外挑战赛",
    "superstar international": "超级明星国际赛",
    "benson and hedges championship": "本森-海吉斯锦标赛",
    "hong kong masters": "香港大师赛", "world masters": "世界大师赛",
    "6-reds world championship": "六红球世界锦标赛",
    "world cup": "世界杯", "world seniors championship": "世界元老锦标赛",
    "seniors masters": "元老大师赛", "uk seniors championship": "英国元老锦标赛",
    "world series of snooker": "世界斯诺克系列赛",
    "masters qualifying event": "大师赛资格赛",
    "scottish masters": "苏格兰大师赛",
    "scottish professional championship": "苏格兰职业锦标赛",
    "world matchplay": "世界对抗赛", "humo masters": "Humo 大师赛",
    "world snooker league": "世界斯诺克联赛",
    "top rank classic": "Top Rank 经典赛",
}

# 次级排名赛分站：PTC - Event 1 / European Tour - Event 4 / Asian Tour - Event 2
_TOUR_EVENT_RE = re.compile(
    r"^(players tour championship|ptc|european tour|asian tour|uk tour)"
    r"\s*-\s*event\s*(\d+)$", re.I)
_TOUR_EVENT_ZH = {
    "players tour championship": "球员巡回锦标赛",
    "ptc": "PTC", "european tour": "欧洲巡回赛",
    "asian tour": "亚洲巡回赛", "uk tour": "英国巡回赛",
}

# 三大赛（生涯冠军榜专用，按赛事全名精确匹配）
TRIPLE_CROWN_EVENTS = {"world championship", "uk championship", "masters"}


def event_zh(name_en):
    """
    历史赛事名 → 中文。用于 CueTracker 生涯夺冠清单（形如 "2024 World Grand Prix"）。
    查不到时原样返回英文名，保证不会显示空白。
    """
    if not name_en:
        return ""
    s = re.sub(r"\s+", " ", str(name_en)).strip()
    s = re.sub(r"^\d{4}\s+", "", s)          # 去掉年份前缀
    s = re.sub(r"\s*\(\d{4}\)\s*$", "", s)   # 去掉尾部 (2024)
    key = s.lower().strip()

    m = _TOUR_EVENT_RE.match(key)
    if m:
        return f"{_TOUR_EVENT_ZH[m.group(1).lower()]} 分站赛 {int(m.group(2))}"
    if key in HISTORIC_EVENTS:
        return HISTORIC_EVENTS[key]
    if key in EVENTS:
        return EVENTS[key]
    return s


STAGE_MAP = {
    "stage one/wk1": "第一阶段 第1周", "stage one/wk2": "第一阶段 第2周",
    "stage one/wk3": "第一阶段 第3周", "stage two/wk1": "第二阶段 第1周",
    "stage two/wk2": "第二阶段 第2周",
    "stage three & final": "第三阶段及决赛",
    "stage one": "第一阶段", "stage two": "第二阶段", "stage three": "第三阶段",
}

# ---------------------------------------------------------------- 城市 / 国家
CITIES = {
    "Leicester": "莱斯特", "Shanghai": "上海", "Taiyuan City": "太原",
    "Wuhan": "武汉", "Cheltenham": "切尔滕纳姆", "Brentwood": "布伦特伍德",
    "Belfast": "贝尔法斯特", "Nanjing": "南京", "Berlin": "柏林",
    "Wigan": "威根", "York": "约克", "Blackpool": "布莱克浦",
    "Edinburgh": "爱丁堡", "London": "伦敦", "Sheffield": "谢菲尔德",
    "Llandudno": "兰迪德诺", "Hong Kong": "香港", "Telford": "特尔福德",
    "Manchester": "曼彻斯特", "Shenzen": "深圳",
    "Yushan, Jiangxi Province": "江西玉山",
}

COUNTRIES = {
    "England": "英格兰", "China": "中国", "Northern Ireland": "北爱尔兰",
    "Scotland": "苏格兰", "Wales": "威尔士", "Germany": "德国",
    "Hong Kong": "中国香港", "Belgium": "比利时", "Australia": "澳大利亚",
    "Austria": "奥地利", "Brazil": "巴西", "Canada": "加拿大",
    "Switzerland": "瑞士", "Egypt": "埃及", "India": "印度",
    "Iran": "伊朗", "Ireland": "爱尔兰", "Latvia": "拉脱维亚",
    "Poland": "波兰", "Thailand": "泰国", "Ukraine": "乌克兰",
    "Malta": "马耳他", "Norway": "挪威", "Finland": "芬兰",
    "Netherlands": "荷兰", "France": "法国", "Spain": "西班牙",
    "Cyprus": "塞浦路斯", "Pakistan": "巴基斯坦", "Malaysia": "马来西亚",
    "Singapore": "新加坡", "Qatar": "卡塔尔", "Turkey": "土耳其",
}

# 三字母国家代码 → 中文
COUNTRY_CODES = {
    "ENG": "英格兰", "SCT": "苏格兰", "WAL": "威尔士", "NIR": "北爱尔兰",
    "IRL": "爱尔兰", "CHN": "中国", "HKG": "中国香港", "AUS": "澳大利亚",
    "BEL": "比利时", "AUT": "奥地利", "BRA": "巴西", "CAN": "加拿大",
    "CHE": "瑞士", "EGY": "埃及", "IND": "印度", "IRN": "伊朗",
    "LVA": "拉脱维亚", "POL": "波兰", "THA": "泰国", "UKR": "乌克兰",
    "MLT": "马耳他", "NOR": "挪威", "FIN": "芬兰", "NLD": "荷兰",
    "FRA": "法国", "ESP": "西班牙", "CYP": "塞浦路斯", "PAK": "巴基斯坦",
    "MYS": "马来西亚", "SGP": "新加坡", "QAT": "卡塔尔", "TUR": "土耳其",
    "GER": "德国", "DEU": "德国",
}

# 三字母国家代码 → 英文全称（用于国家列的英文对照）
COUNTRY_CODE_EN = {
    "ENG": "England", "SCT": "Scotland", "WAL": "Wales",
    "NIR": "Northern Ireland", "IRL": "Ireland", "CHN": "China",
    "HKG": "Hong Kong, China", "AUS": "Australia", "BEL": "Belgium",
    "AUT": "Austria", "BRA": "Brazil", "CAN": "Canada", "CHE": "Switzerland",
    "EGY": "Egypt", "IND": "India", "IRN": "Iran", "LVA": "Latvia",
    "POL": "Poland", "THA": "Thailand", "UKR": "Ukraine", "MLT": "Malta",
    "NOR": "Norway", "FIN": "Finland", "NLD": "Netherlands", "FRA": "France",
    "ESP": "Spain", "CYP": "Cyprus", "PAK": "Pakistan", "MYS": "Malaysia",
    "SGP": "Singapore", "QAT": "Qatar", "TUR": "Turkey", "GER": "Germany",
    "DEU": "Germany", "MDA": "Moldova", "ZAF": "South Africa",
    "NZL": "New Zealand", "JPN": "Japan", "KOR": "South Korea",
}


def country_code_en(code):
    c = (code or "").upper()
    return COUNTRY_CODE_EN.get(c, c)


# ---------------------------------------------------------------- 轮次 / 状态
ROUNDS = {
    "final": "决赛", "semi finals": "半决赛", "semi final": "半决赛",
    "quarter finals": "1/4决赛", "quarter final": "1/4决赛",
    "round 1": "第一轮", "round 2": "第二轮", "round 3": "第三轮",
    "round 4": "第四轮", "round 5": "第五轮", "round 6": "第六轮",
    "last 16": "16强", "last 32": "32强", "last 64": "64强",
    "last 128": "128强", "last 8": "8强", "last 4": "4强",
    "wildcard round": "外卡轮", "pre-qualifier round": "预选资格轮",
    "league phase": "小组循环赛", "round robin": "循环赛",
    "stage one": "第一阶段", "stage two": "第二阶段", "stage three": "第三阶段",
}
HELD_OVER = "延期进行"

STATUS = {
    "Completed": "已结束", "Scheduled": "未开始", "In Progress": "进行中",
    "Live": "进行中", "Postponed": "已推迟", "Cancelled": "已取消",
    "Walkover": "对手弃赛",
}


# ---------------------------------------------------------------- 工具函数
def player_zh(name_en):
    """球员英文名 → 中文名；未收录时返回空串由调用方回退。"""
    if not name_en:
        return ""
    key = re.sub(r"\s+", " ", str(name_en)).strip()
    if key in PLAYERS:
        return PLAYERS[key]
    if key in PLAYERS_EXTRA:
        return PLAYERS_EXTRA[key]
    if key in PLAYERS_LEGACY:
        return PLAYERS_LEGACY[key]
    m = WILDCARD_RE.match(key)
    if m:
        return f"中国外卡 {m.group(1)}"
    return ""


def slugify(name):
    """球员全名 → CueTracker 风格的 URL slug，与 fetch_titles.py 保持一致。"""
    s = (name or "").lower().replace("'", "").replace("\u2019", "").replace(".", "")
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _strip_stage(name):
    """抽离括号内的阶段信息，返回 (剩余名称, 阶段原文)。"""
    m = re.search(r"\(([^)]*)\)\s*$", name)
    if not m:
        return name, ""
    return name[:m.start()].strip(), m.group(1).strip()


def tournament_core(name_en):
    """
    赛事全名 → 规范化核心名（小写）。
    剥离赞助商、阶段后缀、资格赛后缀与年份，用于查表。
    例："BetVictor Championship League Snooker 2026 (Stage One/WK1)" →
        "championship league snooker"
    """
    if not name_en:
        return ""
    s = re.sub(r"\s+", " ", str(name_en)).strip()
    s, _ = _strip_stage(s)
    s = re.sub(r"\s+qualifiers?\s*$", "", s, flags=re.I).strip()
    s = _strip_sponsor(s)
    s = re.sub(r"\b(19|20)\d{2}(/\d{2,4})?\s*$", "", s).strip()
    return re.sub(r"\s+", " ", s).lower()


def _strip_sponsor(name):
    s = name
    for sp in sorted(SPONSORS, key=len, reverse=True):
        if s.startswith(sp + " "):
            s = s[len(sp):].strip()
            break
    return s


def tournament_zh(name_en):
    """赛事全名 → 中文名。先剥赞助商/年份，再查核心名，最后拼后缀。"""
    if not name_en:
        return ""
    s = re.sub(r"\s+", " ", str(name_en)).strip()

    # 1) 抽离括号内的阶段信息
    stage_zh = ""
    mstage = re.search(r"\(([^)]*)\)\s*$", s)
    if mstage:
        raw = mstage.group(1).strip()
        stage_zh = STAGE_MAP.get(raw.lower())
        if not stage_zh:
            stage_zh = STAGE_MAP.get(re.sub(r"\s+", "", raw).lower(), raw)
        s = s[:mstage.start()].strip()

    # 2) 资格赛后缀
    is_qual = False
    mq = re.search(r"\s+qualifiers?\s*$", s, re.I)
    if mq:
        is_qual = True
        s = s[:mq.start()].strip()

    # 3) 剥赞助商
    s = _strip_sponsor(s)

    # 4) 去掉年份
    s = re.sub(r"\b(19|20)\d{2}(/\d{2,4})?\s*$", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()

    core = EVENTS.get(s.lower())
    if not core:
        core = s  # 未收录则回退英文核心名

    out = core
    if is_qual:
        out += "资格赛"
    if stage_zh:
        out += f"（{stage_zh}）"
    return out


def city_zh(city_en):
    if not city_en:
        return ""
    key = re.sub(r"\s+", " ", str(city_en)).strip()
    return CITIES.get(key, "")


def country_zh(country_en):
    if not country_en:
        return ""
    key = re.sub(r"\s+", " ", str(country_en)).strip()
    return COUNTRIES.get(key, "")


def country_code_zh(code):
    return COUNTRY_CODES.get((code or "").upper(), "")


def round_zh(round_en):
    if not round_en:
        return ""
    s = re.sub(r"\s+", " ", str(round_en)).strip()

    # 处理 "Round 1 (Held Over)" / "League Phase (STAGE ONE)"
    suffix = ""
    m = re.search(r"\(([^)]*)\)\s*$", s)
    if m:
        inner = m.group(1).strip()
        base = s[:m.start()].strip()
        if re.search(r"held\s*over", inner, re.I):
            suffix = HELD_OVER
            s = base
        else:
            inner_key = inner.lower()
            if "stage" in inner_key:
                s = base
                inner_key = re.sub(r"\s*/\s*", "/", inner_key)
                suffix = STAGE_MAP.get(inner_key, STAGE_MAP.get(
                    re.sub(r"\s+", " ", inner_key), inner))
            else:
                suffix = inner
    s = re.sub(r"\s+", " ", s).strip()
    core = ROUNDS.get(s.lower(), s)
    return f"{core}（{suffix}）" if suffix else core


def status_zh(status_en):
    return STATUS.get(status_en, status_en or "")


if __name__ == "__main__":
    # 自检
    tests = [
        "BetVictor Championship League Snooker 2026 (Stage One/WK1)",
        "China Open 2026 Qualifiers",
        "Johnstone's Paint Masters 2027",
        "Unibet British Open 2026",
        "TAOM Shoot Out 2026",
        "World Championship 2027",
        "MachineSeeker German Masters 2027 Qualifiers",
    ]
    for t in tests:
        print(f"{t}\n   → {tournament_zh(t)}")
    print()
    for r in ["Final", "Semi Finals", "Round 1 (Held Over)",
              "League Phase (STAGE ONE)", "Quarter Finals", "Wildcard Round"]:
        print(f"{r} → {round_zh(r)}")
