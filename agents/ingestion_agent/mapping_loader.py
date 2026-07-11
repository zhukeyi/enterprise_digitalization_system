"""字段映射加载器（P2a / MVS 核心）。

从 ``field_mapping.yaml`` 加载 :class:`FieldMapping`（P0 契约），并在无配置时
生成「identity 映射」兜底——把每个 Excel 表头直接作为规范化字段名，保证 MVS
在零配置下也能跑通「上传即入库」。

复用 ``shared.contracts.connector_contract`` 的真实 API
（``FieldMapping`` / ``FieldMappingRule`` / ``apply_field_mapping``），不再引入
任何契约里不存在的类（早期草稿误用了 ``DocType`` / ``FieldRule``，已移除）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from shared.contracts.connector_contract import (
    CanonicalDocument,
    FieldMapping,
    FieldMappingRule,
    apply_field_mapping,
)

# 表头 → 字段名的规范化：把空白与连字符压成下划线。
_HEADER_SLUG_RE = re.compile(r"[\s\-]+")


def normalize_field_name(header: str) -> str:
    """把表头规范成稳定的字段名：去首尾空白、内部空白/连字符转下划线。"""
    return _HEADER_SLUG_RE.sub("_", header.strip())


def build_identity_mapping(
    headers: list[str],
    *,
    source_system: str = "excel_upload",
    doc_type: str = "excel_upload",
    schema_version: str = "1.0.0",
) -> FieldMapping:
    """为一组表头生成 identity 映射（列名 → 规范化列名）。

    MVS 零配置路径：上传的 Excel 不需要任何 YAML 即可入库，列名即字段名。
    """
    rules = [
        FieldMappingRule(
            source_path=h,
            target_field=normalize_field_name(h),
            required=False,
            transform=None,
        )
        for h in headers
        if h  # 跳过空表头
    ]
    return FieldMapping(
        schema_version=schema_version,
        connector_id=source_system,
        doc_type=doc_type,
        rules=rules,
    )


def normalize_rows(
    headers: list[str], rows: list[dict[str, Any]], *, doc_type: str = "excel_upload"
) -> list[CanonicalDocument]:
    """把一组原始行（header→value 字典）经 identity 映射归一化为 CanonicalDocument 列表。

    纯函数，不触碰数据库 / 向量库，便于单元测试与复用。
    """
    mapping = build_identity_mapping(headers, doc_type=doc_type)
    return [apply_field_mapping(row, mapping) for row in rows]


def load_field_mapping(path: str | Path) -> FieldMapping:
    """从 YAML 文件加载 :class:`FieldMapping`。

    兼容两种结构：
    * 顶层直接是 ``{connector_id, doc_type, schema_version, rules:[...]}``；
    * 顶层以 connector_id 为键的字典（取第一个含 ``rules`` 的子块）。
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"字段映射文件格式非法: {path}")

    # 结构二：顶层是 {connector_id: {...}}，且没有 rules 键。
    if "rules" not in raw:
        for key, val in raw.items():
            if isinstance(val, dict) and "rules" in val:
                raw = {"connector_id": key, **val}
                break
        else:
            raise ValueError(f"字段映射文件缺少 rules: {path}")

    return coerce_rules_dict(raw)


def coerce_rules_dict(data: dict[str, Any]) -> FieldMapping:
    """从已解析的 dict 构造 FieldMapping（供内存态调用 / 测试复用）。"""
    rules: list[FieldMappingRule] = []
    for item in data.get("rules", []):
        if not isinstance(item, dict):
            continue
        rules.append(
            FieldMappingRule(
                source_path=item["source_path"],
                target_field=item["target_field"],
                required=bool(item.get("required", False)),
                transform=item.get("transform"),
            )
        )
    return FieldMapping(
        schema_version=data.get("schema_version", "1.0.0"),
        connector_id=data.get("connector_id", data.get("source_system", "unknown")),
        doc_type=data.get("doc_type", "generic"),
        rules=rules,
    )


__all__ = [
    "build_identity_mapping",
    "coerce_rules_dict",
    "load_field_mapping",
    "normalize_field_name",
    "normalize_rows",
]
