"""P2b 三层字段归一化测试：L1 别名 / L2 值变换 / L3 去重+实体归一。"""

from __future__ import annotations

from agents.ingestion_agent.normalization import (
    apply_aliases,
    normalize_table_rows,
    normalize_text_block,
)


def test_apply_aliases_maps_chinese_to_canonical() -> None:
    headers = ["客户名称", "Order-No", "所在城市"]
    assert apply_aliases(headers) == ["customer_name", "order_no", "city"]


def test_normalize_table_rows_alias_and_numeric() -> None:
    headers = ["客户名称", "合同金额"]
    rows = [{"客户名称": "阿里巴巴", "合同金额": "¥1,250,000"}]
    docs = normalize_table_rows(headers, rows, doc_type="sales")
    assert len(docs) == 1
    fields = docs[0].fields
    assert fields["customer_name"] == "阿里巴巴"
    assert fields["contract_amount"] == 1250000.0


def test_normalize_table_rows_drops_duplicate_rows() -> None:
    headers = ["客户名称"]
    rows = [{"客户名称": "阿里巴巴"}, {"客户名称": "阿里巴巴"}]
    docs = normalize_table_rows(headers, rows)
    assert len(docs) == 1


def test_normalize_table_rows_entity_map() -> None:
    headers = ["城市"]
    rows = [{"城市": "上海市"}]
    docs = normalize_table_rows(headers, rows)
    assert docs[0].fields["city"] == "上海"


def test_normalize_table_rows_skips_empty_rows() -> None:
    headers = ["客户名称"]
    rows = [{"客户名称": ""}, {"客户名称": None}]
    assert normalize_table_rows(headers, rows) == []


def test_normalize_text_block_collapses_and_dedups() -> None:
    raw = "段落一\n段落一\n\n段落二"
    out = normalize_text_block(raw)
    assert out.count("段落一") == 1  # 连续重复行已去重
    assert "段落二" in out
    assert "\n\n\n" not in out  # 多空行已合并


def test_normalize_table_rows_date_to_iso() -> None:
    headers = ["签约日期"]
    rows = [{"签约日期": "2024-01-15"}]
    docs = normalize_table_rows(headers, rows)
    assert docs[0].fields["sign_date"] == "2024-01-15"
