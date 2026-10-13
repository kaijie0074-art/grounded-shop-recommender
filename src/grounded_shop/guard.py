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


def _robust_json(raw: str) -> dict:
    """R1 硬化：真实模型常把 JSON 包进 ```json 围栏或夹带前后缀噪声。

    深潜 Q2 修复：严格 json.loads 令围栏输出全部降级 parse_error → 兜底模板，
    误杀率 100%（实测 glm-4-flash 新提示词下 3/3 触发）。三段式解析：
    直接解析 → 剥围栏 → 截取首个 { 到末个 }。
    """
    s = raw.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    if s.startswith("```"):
        lines = s.splitlines()
        body = lines[1:]
        if body and body[-1].strip().startswith("```"):
            body = body[:-1]
        try:
            return json.loads("\n".join(body))
        except Exception:
            pass
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        return json.loads(s[i:j + 1])
    raise ValueError("no JSON object found")


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
# 连接词豁免（深潜 Q2' 发现的误杀类："以其锅贴""锅贴和饺子""则是一家小店"）：
# 紧邻后缀词的 以/和/家 等连接字引出的是普通短语，不是店名；库内店名无一以此收尾。
SUFFIX_CONNECTORS = ("以", "和", "与", "或", "跟", "配", "加", "做", "家")
_SUFFIXES = sorted(NAME_SUFFIX.split("|"), key=len, reverse=True)


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
        # 连接词豁免：后缀前紧邻连接字（和饺子/一家小店/以其锅贴）→ 普通短语。
        # "和饺子馆"（子+馆，连接字不紧邻后缀）不受影响。
        exempt = False
        for suf in _SUFFIXES:
            if token.endswith(suf):
                head = token[: -len(suf)]
                exempt = bool(head) and (head[-1] in SUFFIX_CONNECTORS or head.endswith("以其"))
                break
        if not exempt:
            suspects.add(token)
    return suspects

LATIN_SUSPECT = re.compile(r"[A-Za-z][A-Za-z'&·\-]{3,}")
CJK_RUN = re.compile(r"[\u4e00-\u9fa5]{2,}")


def _norm_name(s: str) -> str:
    """比较用归一化：只保留 CJK 与字母数字（去括号、间隔号等符号）。"""
    return "".join(c for c in s if "\u4e00" <= c <= "\u9fa5" or c.isalnum())


def _levenshtein_le(a: str, b: str, limit: int = 1) -> bool:
    """带剪枝的编辑距离：distance(a, b) <= limit 时 True。"""
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            row_best = min(row_best, v)
        if row_best > limit:
            return False
        prev = cur
    return prev[-1] <= limit


def extract_near_miss_shopnames(text: str, candidates: list[Shop], all_names: list[str]) -> set[str]:
    """R4b：近邻编造检测——与库内任一店名（归一化后）编辑距离 ≤1 的窗口。

    深潜研究 2026-10-14 Q2 发现的绕过面：改一个字的后缀谐音变体
    （金玉家常水铰/王姐家尝菜）不再命中任何店名后缀，pass-2 全漏。
    变体名几乎总是从真名派生（保留绝大多数字符），而合法短语与店名
    距离 ≤1 的概率极低（"想吃家常菜" vs "王姐家常菜" 距离 2）。
    阈值取 1：宁紧勿松，误杀代价是降级兜底（安全）。
    繁体/多字改写（順記混沌，距离 4）仍会绕过——已记录为已知缺口。
    """
    ref = {_norm_name(n) for n in list(all_names) + [s.name for s in candidates]}
    ref.discard("")
    if not ref:
        return set()
    scrubbed = text
    for n in sorted({s.name for s in candidates}, key=len, reverse=True):
        scrubbed = scrubbed.replace(n, "§")
    found: set[str] = set()
    for run_m in CJK_RUN.finditer(scrubbed):
        run = _norm_name(run_m.group(0))
        for name in ref:
            L = len(name)
            for w in (L - 1, L, L + 1):
                if w < 2 or w > len(run):
                    continue
                for s in range(len(run) - w + 1):
                    if _levenshtein_le(run[s:s + w], name, 1):
                        found.add(run[s:s + w])
                        break
    return found


def extract_latin_suspects(text: str) -> set[str]:
    """R4c：拉丁字母连串（≥4 字符）视为疑似编造（Shun Ji Wonton 这类跨语言写法）。

    本域输出为中文推荐语；正文中出现 ≥4 字符的拉丁串几乎只有编造店名的
    外语写法一种来源。AI 标识（"AI"，2 字符）不受影响。"""
    return {m.group(0) for m in LATIN_SUSPECT.finditer(text)}



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
        data = _robust_json(raw)
        answer = str(data["answer"])
        recommended = [str(n) for n in data.get("recommended", [])]
    except Exception:
        return GuardVerdict(ok=False, parse_error=True)

    # R2：recommended 必须是候选子集
    violations = {n for n in recommended if n not in candidate_names}
    # R3：库内其他店混进 answer
    text_mentions = extract_mentions(answer, all_names)
    violations |= {n for n in text_mentions if n not in candidate_names}
    # R4：编造店名（后缀启发式）
    violations |= extract_suspect_shopnames(answer, candidates)
    # R4b：近邻编造（错一字谐音变体）；R4c：拉丁字母串（跨语言写法）
    violations |= extract_near_miss_shopnames(answer, candidates, all_names)
    violations |= extract_latin_suspects(answer)
    # R5：自申报 mentions——正文里出现过的每个店名必须逐字申报，且 ⊆ 候选集。
    # 把"正文未知实体"转成结构化字段锚定：无后缀编造名（台东往事小院）只有
    # 靠模型如实申报才能被机械捕获（申报可靠性实测见 docs/research/deep-dive-20261014.md Q7）。
    declared = data.get("mentions")
    # 缺失 mentions 视同申报为空：正文里出现任何候选店名都算漏报（强制申报习惯）
    declared_set = {str(m) for m in declared} if isinstance(declared, list) else set()
    violations |= declared_set - candidate_names  # R5a：申报了候选外的名字
    violations |= extract_mentions(answer, candidate_names) - declared_set  # R5b：漏报
    if violations:
        return GuardVerdict(ok=False, answer=answer, recommended=recommended, violations=violations)
    return GuardVerdict(ok=True, answer=answer, recommended=[n for n in recommended if n in candidate_names])


def text_violations(text: str, candidates: list[Shop], all_names: list[str]) -> set[str]:
    """对裸文本跑全部文本类规则（R3/R4/R4b/R4c）——剥句后复检用。"""
    cand_names = {s.name for s in candidates}
    violations = {n for n in extract_mentions(text, all_names) if n not in cand_names}
    violations |= extract_suspect_shopnames(text, candidates)
    violations |= extract_near_miss_shopnames(text, candidates, all_names)
    violations |= extract_latin_suspects(text)
    return violations


def strip_violating_sentences(text: str, violations: set[str], all_names: list[str],
                              candidates: list[Shop] | None = None) -> str:
    """锚定式剥句（深潜 Q2' 修复）：只保留同时满足两个条件的句子——
    1. 不含任何违规串；2. 锚定了候选店名（提及至少一个候选）。

    旧版"只删违规句"会把未被机械规则识别的编造句留在输出里（实测泄漏：
    "台东往事小院如果还在的话…"整句保留）。白名单式剥句让降级路径的
    每个事实句都锚定在候选集上；全空则由上层降级到零 LLM 模板。
    剥离后跑一次全量文本规则（text_violations）做双保险。
    """
    if not text:
        return ""
    cand = candidates if candidates is not None else []
    cand_names = {s.name for s in cand} or set(all_names)
    sentences = [s for s in SENTENCE_SPLIT.split(text) if s.strip()]
    kept = [s for s in sentences
            if not any(v in s for v in violations) and any(c in s for c in cand_names)]
    out = "\n".join(kept)
    if not out:
        return ""
    if text_violations(out, cand, all_names):
        return ""
    return out
