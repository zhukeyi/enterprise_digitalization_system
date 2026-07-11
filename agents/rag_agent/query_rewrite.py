"""RAG 查询改写（P3 / T3）。

规则式改写：实体归一 + 同义词扩展 + 停用词移除。无 LLM 依赖，确定性、
可测试，适合 ARM 上低延迟（与重排配合提升召回/精度）。

语义级改写（HyDE / Multi-Query / LLM 生成）依赖大模型推理，留待 P6b GPU
微服务（避免在 11G ARM 单机与 Dify/Qdrant 争资源）。

词法采用与嵌入/Reranker 一致的「CJK 逐字 + ASCII 按词」分词，因此同义词以
**短语子串命中**方式扩展（如查询含「总部」→ 追加「坐落于/设在/所在地」等短语
的字符），保证 char-level 嵌入也能受益。
"""

from __future__ import annotations

from agents.rag_agent.reranker import tokenize

# 多字停用词（先整串移除再分词）
_MULTI_STOPWORDS = {
    "请问",
    "帮我",
    "我想",
    "查询",
    "检索",
    "一下",
    "什么",
    "哪些",
    "怎么",
    "如何",
    "怎样",
    "为什么",
    "能不能",
    "是否可以",
    "有没有",
    "是多少",
    "位于哪里",
    "在哪里",
}

# 单字停用词（分词后丢弃）。仅含功能字，不含内容字（上/下/中/内/外 等会构成
# 地名、方位等语义，必须保留）。
_CHAR_STOPWORDS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "及",
    "或",
    "有",
    "吗",
    "呢",
    "啊",
    "呀",
    "吧",
    "哦",
    "这",
    "那",
    "个",
    "些",
    "我",
    "你",
    "他",
    "她",
    "它",
    "们",
    "请",
    "问",
    "帮",
    "查",
    "看",
    "给",
    "对",
    "为",
    "把",
    "被",
    "让",
    "向",
    "从",
    "到",
    "之",
    "其",
    "等",
    "将",
    "已",
    "并",
    "而",
    "a",
    "an",
    "the",
    "of",
    "to",
    "and",
    "for",
    "is",
    "are",
}

# 同义词扩展表（短语 → 追加短语）。命中即把追加短语的字符并入查询。
_SYNONYMS: dict[str, list[str]] = {
    "总部": ["总部", "坐落于", "设在", "所在地", "位于"],
    "客户": ["客户", "顾客", "买方", "公司", "企业"],
    "合同": ["合同", "合约", "协议", "订单"],
    "金额": ["金额", "总价", "总额", "费用", "价钱"],
    "城市": ["城市", "市区", "地区"],
    "省份": ["省份", "省"],
    "地址": ["地址", "位置", "所在地"],
    "电话": ["电话", "联系方式", "手机", "座机"],
    "员工": ["员工", "人员", "职员", "同事"],
    "收入": ["收入", "营收", "营业额", "销售额"],
}

# 实体归一（与 ingestion.normalization.DEFAULT_ENTITY_MAP 对齐的子集；
# 本地维护以避免 rag_agent 反向依赖 ingestion_agent）。
_ENTITY_MAP: dict[str, str] = {
    "上海市": "上海",
    "北京市": "北京",
    "深圳市": "深圳",
    "广州市": "广州",
    "杭州市": "杭州",
    "成都市": "成都",
    "南京市": "南京",
}


class QueryRewriter:
    """规则式查询改写器。"""

    def __init__(
        self,
        synonyms: dict[str, list[str]] | None = None,
        stopwords: set[str] | None = None,
        entity_map: dict[str, str] | None = None,
    ) -> None:
        self.synonyms = synonyms if synonyms is not None else _SYNONYMS
        self.char_stopwords = stopwords if stopwords is not None else _CHAR_STOPWORDS
        self.entity_map = entity_map if entity_map is not None else _ENTITY_MAP

    def rewrite(self, query: str) -> str:
        """返回改写后的查询（空格分隔的 token 串）。"""
        if not query or not query.strip():
            return query

        q = query
        # 1) 实体归一（短语子串替换）
        for k, v in self.entity_map.items():
            if k in q:
                q = q.replace(k, v)

        # 2) 多字停用词整串移除
        for sw in _MULTI_STOPWORDS:
            if sw in q:
                q = q.replace(sw, " ")

        # 3) 同义词扩展：短语命中即追加其字符（去重）
        seen: set[str] = set()
        extra: list[str] = []
        for key, syns in self.synonyms.items():
            if key in q:
                for phrase in syns:
                    for ch in tokenize(phrase):
                        if ch not in seen:
                            seen.add(ch)
                            extra.append(ch)

        # 4) 基础 token：原查询字符级分词，丢单字停用词
        base = [ch for ch in tokenize(q) if ch not in self.char_stopwords]
        merged = base + [ch for ch in extra if ch not in set(base)]
        return " ".join(merged) if merged else query


_default_rewriter: QueryRewriter | None = None


def get_default_rewriter() -> QueryRewriter:
    """返回默认改写器（单例）。"""
    global _default_rewriter
    if _default_rewriter is None:
        _default_rewriter = QueryRewriter()
    return _default_rewriter


__all__ = ["QueryRewriter", "get_default_rewriter"]
