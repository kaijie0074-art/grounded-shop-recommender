"""口语查询解析：区域与标签的词典归一化。

不做 NLU：词典 + 规则即可解释、可调参、零幻觉（问题报告 §2.3 方案 C——
事实层不交给模型，解析层同样不交给模型）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 长词优先匹配，避免"台东八路"被"台东"截断后语义丢失
AREA_LEXICON: dict[str, str] = {
    "台东八路": "台东", "台东三路": "台东", "台东五路": "台东", "台东六路": "台东",
    "台东": "台东", "步行街": "台东", "利群": "台东", "人和路": "台东",
    "郭口路": "台东", "昆明路": "台东", "菜市二路": "台东", "沈阳支路": "台东",
    "威海路": "威海路",
    "营口路": "营口路", "洮南路": "营口路",
    "登州路": "登州路", "啤酒街": "登州路",
    "延安二路": "延安二路", "福山路": "延安二路",
    "镇江路": "镇江路", "海泊河": "镇江路", "本溪路": "镇江路",
}

TAG_LEXICON: dict[str, str] = {
    "小海鲜": "海鲜", "海鲜": "海鲜",
    "烤肉": "烧烤", "烤串": "烧烤", "鱿鱼": "烧烤", "烧烤": "烧烤",
    "家常菜": "家常菜", "家常": "家常菜", "炒菜": "家常菜", "盒饭": "快餐",
    "羊肉面": "面食", "辣鸡面": "面食", "拉面": "面食", "面食": "面食", "面": "面食",
    "羊汤": "羊汤",
    "水饺": "饺子", "饺子": "饺子",
    "锅贴": "锅贴",
    "炸肉": "炸串", "炸串": "炸串",
    "馄饨": "馄饨",
    "大排档": "大排档", "排档": "大排档",
    "老字号": "老字号",
    "夜宵": "深夜", "宵夜": "深夜", "夜里": "深夜", "晚上": "深夜", "深夜": "深夜",
    "苍蝇馆子": "苍蝇馆子", "苍蝇馆": "苍蝇馆子", "苍蝇": "苍蝇馆子",
    "小馆": "苍蝇馆子", "小店": "小店",
    "啤酒屋": "啤酒屋", "散啤": "啤酒屋",
    "早餐": "早餐", "早点": "早餐",
    "麻辣烫": "麻辣烫", "小吃": "小吃", "烤鱼": "烤鱼",
    # 以下品类当前种子库无收录：识别后候选为空 → 标准拒答（不猜、不硬推）
    "法餐": "法餐", "日料": "日料", "火锅": "火锅", "素食": "素食",
}

# 青岛其他区/县级市：明显超出当前种子库覆盖范围，直接走"区域未覆盖"拒答
OUT_OF_COVERAGE_AREAS = [
    "李沧", "市南", "崂山", "城阳", "黄岛", "西海岸", "胶州", "即墨", "平度", "莱西", "高新区",
]

KNOWN_TAG_HINT = "海鲜/烧烤/家常菜/面食/饺子/锅贴/炸串/馄饨/大排档/深夜/苍蝇馆子/老字号"


@dataclass
class ParsedQuery:
    areas: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    out_of_coverage: bool = False
    max_price: float | None = None


ANY_TAG = "__any__"  # 泛美食问法："推荐几家好吃的"——不做品类过滤
BUDGET_PATTERN = re.compile(r"人均?(\d{2,3})(?:元)?(?:以内|以下|内)?|预算(\d{2,3})")


def parse_query(text: str) -> ParsedQuery:
    """把口语问法归一化为 {标准区域集合, 标准标签集合, 预算上限}。纯规则，可单测。"""
    pq = ParsedQuery()
    for word, std in sorted(AREA_LEXICON.items(), key=lambda kv: -len(kv[0])):
        if word in text:
            pq.areas.add(std)
    for word, std in sorted(TAG_LEXICON.items(), key=lambda kv: -len(kv[0])):
        if word in text:
            pq.tags.add(std)
    for generic in ("好吃", "美食", "解馋", "随便吃"):
        if generic in text:
            pq.tags.add(ANY_TAG)
    if m := BUDGET_PATTERN.search(text):
        pq.max_price = float(m.group(1) or m.group(2))
    pq.out_of_coverage = any(a in text for a in OUT_OF_COVERAGE_AREAS)
    return pq
