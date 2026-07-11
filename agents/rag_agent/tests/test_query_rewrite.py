"""P3 查询改写单元测试：同义词扩展 + 停用词移除 + 实体归一。"""

from __future__ import annotations

from agents.rag_agent.query_rewrite import QueryRewriter, get_default_rewriter


def test_synonym_expansion_appends_chars() -> None:
    """「总部 这里」应扩展出坐落于/设在/所在地 的字符（坐/落/设/在/所/地）。"""
    out = QueryRewriter().rewrite("总部 这里")
    assert "总" in out and "部" in out  # 原词保留
    assert "坐" in out and "落" in out  # 来自「坐落于」
    assert "设" in out and "在" in out and "所" in out and "地" in out  # 来自「设在/所在地」
    assert "里" in out and "这" not in out  # 原查询字符保留（这 为停用词已去）


def test_stopwords_removed() -> None:
    """单字与多字停用词应被移除，关键词保留。"""
    out = QueryRewriter().rewrite("杭州 的 客户 是 哪些")
    assert "的" not in out
    assert "是" not in out
    assert "哪些" not in out
    assert "杭" in out and "州" in out
    assert "客" in out and "户" in out


def test_entity_normalization() -> None:
    """「上海市」应归一为「上海」，且不残留「上海市」。"""
    out = QueryRewriter().rewrite("上海市 客户 名单")
    assert "上" in out and "海" in out
    assert "上海市" not in out
    assert "客" in out and "户" in out


def test_empty_query_unchanged() -> None:
    assert QueryRewriter().rewrite("") == ""
    assert QueryRewriter().rewrite("   ") == "   "


def test_default_rewriter_is_singleton() -> None:
    assert get_default_rewriter() is get_default_rewriter()
