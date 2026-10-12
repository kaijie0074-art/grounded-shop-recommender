"""回校器（guard）：输出事实性的机械验证层——本仓库的心脏。

机制源头（docs/research-opensource.md）：
- guardrails 的 validator + on-fail 动作（reask / filter / fix）
- ragas faithfulness 的"答案 claims 必须落在给定上下文内"思想——
  这里把"打分评估"升级为"硬校验"：违规即拦截，不给 0.9 分的侥幸。

判定规则（可机械验收）：
  R1 输出必须可解析为 {"answer": str, "recommended": [str]}
  R2 recommended ⊆ 候选集店名（结构性夹带拦截）
  R3 answer 文本中出现的任何库内店名 ∈ 候选集（库内串店拦截）
  R4 answer 文本中疑似店名的 token（后缀模式启发式）∈ 候选集 ∪ 豁免词典（编造店名拦截）
处置链：重试一次 → 剥离违规句 → 兜底模板（零 LLM）。

R4 取舍说明：启发式必然存在误杀。误杀的代价是降级到零 LLM 模板（安全），
漏杀的代价是编造店名到达用户（信任归零）。宁可误杀。
"""
from __future__ import annotations

import json
import re

from .models import Shop

SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])\s*|\n")

# 店名常见后缀/品类词（R4 启发式）
NAME_SUFFIX = (
    "海鲜楼|大排档|烧烤城|啤酒屋|麻辣烫|烤肉|烤鱼|拉面|馄饨|水饺|饺子|锅贴|炸串|"
    "羊汤|面馆|菜馆|食堂|厨房|小厨|烤肉店|总店|分店|老店|旗舰店|店|馆|楼|舫|铺|坊|斋|轩|阁|庄|城"
)
SUSPECT_PATTERN = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9·]{2,14}(?:" + NAME_SUFFIX + ")")
VARIANT_PATTERN = re.compile(r"[\u4e00-\u9fa5]{2,14}(?:分店|总店|新店|老店|旗舰店|二店|三店|[0-9一二三]店)")
# 豁免：常用普通词汇（非店名）
COMMON_WORDS = {
    "小店", "老店", "店铺", "门店", "店名", "营业", "电话", "步行街", "利群",
    "苍蝇馆子", "苍蝇馆", "宝藏店", "靠谱的小店", "几家小店", "这家店", "那家店",
    "台东三路步行街", "数据还在完善中",
}
VERB_PREFIX = ("吃", "喝", "去", "来", "找", "想", "要", "点", "逛", "买", "推荐", "试试", "看看", "挑", "主打")


def extract_mentions(text: str, known_names: list[str]) -> set[str]:
    """找出文本中出现的库内店名。最长优先匹配，防止店名互为子串时误判。"""
    found: set[str] = set()
    remaining = text
    for name in sorted(known_names, key=len, reverse=True):
        if name in remaining:
            found.add(name)
            remaining = remaining.replace(name, "§")
    return found


def extract_suspect_shopnames(text: str, candidates: list[Shop]) -> set[str]:
    """R4：两遍检测，不锚定在候选集上的疑似店名即违规。

    pass-1（变体模式，零启发式）：候选店名后紧跟 分店/总店/新店/旗舰/二店…
    是明确的编造变体（"测试海鲜楼分店"⊃"测试海鲜楼"），直接违规（评审 OB-1）。

    pass-2（后缀启发式）：先抹除文本中完整出现的候选店名（合法提及不参与
    启发式，"给你推荐测试海鲜楼"里的店名片段不误杀），再对剩余文本跑
    店名后缀模式。命中即违规（"老张秘制海鲜楼"这类纯编造名）。
    豁免通道：常用词词典 / 候选 tags 词表及其前缀 / 含"的"短语 / 动词开头短语。
    误杀代价 = 降级到零 LLM 兜底（安全）；漏杀代价 = 编造名到达用户（信任归零）。
    宁可误杀。
    """
    names = [s.name for s in candidates]
    tag_words = {t for s in candidates for t in s.tags}
    suspects: set[str] = set()

    for n in names:
        for m in VARIANT_PATTERN.finditer(text):
            if n in m.group(0):
                suspects.add(m.group(0))

    scrubbed = text
    for n in sorted(names, key=len, reverse=True):
        scrubbed = scrubbed.replace(n, "§")
    for m in SUSPECT_PATTERN.finditer(scrubbed):
        token = m.group(0)
        if token in COMMON_WORDS:
            continue
        if token in tag_words or any(t.startswith(token) for t in tag_words):
            continue
        if "的" in token:  # 店名极少含"的"，含"的"的多为普通短语
            continue
        if any(token.startswith(v) for v in VERB_PREFIX):
            continue
        suspects.add(token)
    return suspects


class GuardVerdict:
    def __init__(self, *, ok: bool, answer: str = "", recommended: list[str] | None = None,
                 violations: set[str] | None = None, parse_error: bool = False):
        self.ok = ok
        self.answer = answer
        self.recommended = recommended or []
        self.violations = violations or set()
        self.parse_error = parse_error


def check_output(raw: str, candidates: list[Shop], all_names: list[str]) -> GuardVerdict:
    candidate_names = {s.name for s in candidates}
    try:
        data = json.loads(raw)
        answer = str(data["answer"])
        recommended = [str(n) for n in data.get("recommended", [])]
    except Exception:
        return GuardVerdict(ok=False, parse_error=True)

    # R2：recommended 必须是候选子集
    violations = {n for n in recommended if n not in candidate_names}
    # R3：库内其他店混进 answer
    text_mentions = extract_mentions(answer, all_names)
    violations |= {n for n in text_mentions if n not in candidate_names}
    # R4：编造店名（启发式）
    violations |= extract_suspect_shopnames(answer, candidates)

    if violations:
        return GuardVerdict(ok=False, answer=answer, recommended=recommended, violations=violations)
    return GuardVerdict(ok=True, answer=answer, recommended=[n for n in recommended if n in candidate_names])


def strip_violating_sentences(text: str, violations: set[str], all_names: list[str]) -> str:
    """删除包含违规店名的句子；若剥离后仍残留违规则返回空串（由上层降级兜底）。"""
    if not text:
        return ""
    sentences = [s for s in SENTENCE_SPLIT.split(text) if s.strip()]
    kept = [s for s in sentences if not any(v in s for v in violations)]
    out = "\n".join(kept)
    # 双保险：剥离后再全量检查一次（含库内店名与启发式）
    residue = extract_mentions(out, all_names) & violations
    residue |= {v for v in violations if v in out}
    if residue:
        return ""
    return out
