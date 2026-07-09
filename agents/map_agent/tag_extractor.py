"""Tag extraction engine — converts marker note text to structured tags.

Strategy:
1. Fast path: keyword regex matching against a curated category map.
2. Fallback: jieba Chinese segmentation, take top-N nouns.

If jieba is unavailable (not installed), falls back to simple character
frequency analysis so the service degrades gracefully.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

logger = logging.getLogger("fde.map.tags")

# ══════════════════════════════════════════════════════════════════
# Keyword → Tag mapping (ordered by priority)
# ══════════════════════════════════════════════════════════════════

_KEYWORD_MAP: list[tuple[str, str]] = [
    # 交通
    (r"火车站|高铁|铁路|轨道|动车|列车", "交通"),
    (r"地铁|公交|客运|枢纽|机场|航班|码头|港口| ferry", "交通"),
    (r"高速|公路|国道|省道|路口|立交|桥", "交通"),
    # 政务
    (r"政府|省委|市委|区委|办公厅|政务|行政中心|街道办|居委会", "政务"),
    # 商业
    (r"商场|购物|商圈|商业街|步行街|百货|超市|便利店| mall", "商业"),
    (r"银行|金融|证券|保险|投资|基金", "商业"),
    # 居住
    (r"小区|住宅|楼盘|居民|公寓|别墅|安置房|城中村", "居住"),
    # 教育
    (r"学校|大学|中学|小学|幼儿园|校区|学院|教育|科研|研究所", "教育"),
    # 医疗
    (r"医院|诊所|卫生院|药房|急救|疾控|卫生中心", "医疗"),
    # 工业
    (r"工厂|园区|产业园|工业园|科技园|孵化器|制造|仓储|物流", "工业"),
    # 文旅
    (r"景区|公园|景点|古镇|遗址|博物馆|纪念馆|旅游|名胜|寺庙|教堂", "文旅"),
    # 地理
    (r"城区|市中心|市区|主城", "城区"),
    (r"郊县|郊区|乡镇|农村|远郊", "郊县"),
    (r"滨水|江边|湖畔|河岸|海岸|水岸", "滨水"),
    (r"山区|山脚|山谷|山腰|山岭", "山区"),
    (r"平原|盆地|高原", "平原"),
    # 规模
    (r"核心|中心|中央|CBD|主城", "核心"),
    (r"次中心|副中心", "次中心"),
    (r"边缘|外围|远郊", "边缘"),
    # 状态
    (r"在建|建设期|施工|工地", "建设期"),
    (r"规划|待建|拟建|计划", "规划中"),
    (r"已开发|成熟|建成|完工", "已开发"),
    # 风险
    (r"人流|客流|人流量|人口密集|拥挤", "高人流"),
    (r"风险|灾害|隐患|危险|塌方|内涝", "风险"),
    (r"低密度|人少|稀疏|空旷", "低密度"),
]

# Pre-compile regex patterns for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), tag) for pattern, tag in _KEYWORD_MAP
]

# Try to import jieba (optional dependency)
_jieba_available = False
try:
    import jieba.posseg as pseg  # type: ignore[import-untyped]

    _jieba_available = True
except ImportError:
    logger.info("jieba not installed, falling back to character-frequency tagging")


def extract(text: str, max_tags: int = 5) -> list[str]:
    """Extract tags from note text.

    Args:
        text: The note text to analyze.
        max_tags: Maximum number of tags to return.

    Returns:
        A deduplicated list of tag strings, ordered by relevance.
    """
    if not text or not text.strip():
        return []

    tags: list[str] = []
    seen: set[str] = set()

    # Phase 1: Keyword matching (fast path)
    for pattern, tag in _COMPILED_PATTERNS:
        if tag not in seen and pattern.search(text):
            tags.append(tag)
            seen.add(tag)
        if len(tags) >= max_tags:
            return tags

    # Phase 2: jieba fallback for unmatched content
    if _jieba_available:
        try:
            words = pseg.cut(text)
            noun_candidates: list[str] = []
            for word, flag in words:
                # Take nouns (n*), proper nouns (nr/ns/nt/nz), and place names
                if flag.startswith("n") and len(word) >= 2 and word not in seen:
                    noun_candidates.append(word)

            # Take top nouns by frequency
            noun_counts = Counter(noun_candidates)
            for word, _ in noun_counts.most_common(max_tags - len(tags)):
                if word not in seen:
                    tags.append(word)
                    seen.add(word)
        except Exception:
            logger.warning("jieba segmentation failed, using raw tags only")
    else:
        # Simple fallback: extract 2-char sequences from Chinese text
        chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
        if chinese_chars:
            # Take first 2-3 char substring as a pseudo-tag
            for chunk in chinese_chars:
                if len(chunk) >= 2:
                    candidate = chunk[:2]
                    if candidate not in seen:
                        tags.append(candidate)
                        seen.add(candidate)
                if len(tags) >= max_tags:
                    break

    return tags[:max_tags]


def extract_tags(text: str, max_tags: int = 5) -> list[str]:
    """Alias for extract() — public API."""
    return extract(text, max_tags)
