"""三层字段归一化（P2b / 完整本地文件入库）。

* **L1 字段名/别名归一化**：把中英文业务表头（如 ``客户名称``）映射到规范英文字段
  （``customer_name``），经真实契约 ``FieldMapping`` / ``apply_field_mapping`` 落地，
  保证与连接器数据同构。
* **L2 值变换 + 类型推断**：去货币符号/千分位 → 数值；常见日期格式 → ISO；编码类
  字段转大写。
* **L3 去重 + 实体归一**：按归一化 payload 哈希去重；少量高频同义词（上海/北京市…）
  归一为统一表述。

所有函数为纯函数，不触碰数据库 / 向量库，便于单元测试与复用。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from typing import Any

from agents.ingestion_agent.mapping_loader import normalize_field_name
from shared.contracts.connector_contract import (
    CanonicalDocument,
    FieldMapping,
    FieldMappingRule,
    apply_field_mapping,
)

# L1 别名表：常见中英文业务表头 → 规范英文字段名
DEFAULT_ALIASES: dict[str, str] = {
    "客户名称": "customer_name",
    "客户": "customer_name",
    "客户名": "customer_name",
    "customer name": "customer_name",
    "customer": "customer_name",
    "订单号": "order_no",
    "订单编号": "order_no",
    "订单单号": "order_no",
    "order no": "order_no",
    "order_no": "order_no",
    "order id": "order_no",
    "联系电话": "phone",
    "电话": "phone",
    "手机号": "phone",
    "phone": "phone",
    "所在城市": "city",
    "城市": "city",
    "city": "city",
    "合同金额": "contract_amount",
    "合同金额rmb": "contract_amount",
    "金额": "amount",
    "amount": "amount",
    "金额rmb": "contract_amount",
    "签约日期": "sign_date",
    "日期": "date",
    "date": "date",
    "产品": "product",
    "产品名称": "product",
    "product": "product",
    "数量": "quantity",
    "quantity": "quantity",
    "负责人": "owner",
    "经办人": "owner",
    "owner": "owner",
}

# L3 实体归一（少量高频同义词）
DEFAULT_ENTITY_MAP: dict[str, str] = {
    "上海市": "上海",
    "北京市": "北京",
    "深圳市": "深圳",
    "广州市": "广州",
    "杭州市": "杭州",
    "成都市": "成都",
    "南京市": "南京",
}

_DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%d/%m/%Y", "%m/%d/%Y"]


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:64]


def _try_iso_date(s: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def apply_aliases(headers: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    """L1：把表头列表映射为规范字段名。"""
    aliases = aliases or DEFAULT_ALIASES
    out: list[str] = []
    for h in headers:
        key = h.strip()
        if key in aliases:
            out.append(aliases[key])
        else:
            norm = normalize_field_name(h)
            out.append(aliases.get(norm, aliases.get(norm.lower(), norm)))
    return out


def _coerce_value(field: str, value: Any) -> Any:
    """L2：单值变换 + 类型推断。"""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        # 数值（去货币符号 / 千分位）
        if re.fullmatch(r"[¥$￥RMB\s]*\d[\d,]*(\.\d+)?", s, re.IGNORECASE):
            try:
                return float(
                    s.replace(",", "")
                    .replace("¥", "")
                    .replace("￥", "")
                    .replace("$", "")
                    .replace("RMB", "")
                    .replace(" ", "")
                )
            except ValueError:
                pass
        # 日期（字段名或值形态命中）→ ISO
        if re.search(r"(date|时间|日期)$", field, re.I) or re.fullmatch(
            r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", s
        ):
            iso = _try_iso_date(s)
            if iso:
                return iso
        # 编码类字段（含 no/code/id）转大写
        if re.search(r"(no|code|id)$", field, re.I) and s.isalnum():
            return s.upper()
        return s
    return value


def normalize_table_rows(
    headers: list[str],
    rows: list[dict[str, Any]],
    *,
    doc_type: str = "file_upload",
    aliases: dict[str, str] | None = None,
    entity_map: dict[str, str] | None = None,
) -> list[CanonicalDocument]:
    """三层归一化：L1 字段名别名 → L2 值变换/类型推断 → L3 去重 + 实体归一。

    返回去重后的 ``CanonicalDocument`` 列表（纯函数）。
    """
    norm_headers = apply_aliases(headers, aliases)
    rules = [
        FieldMappingRule(
            source_path=h,
            target_field=nh,
            required=False,
            transform="to_upper" if re.search(r"(no|code|id)$", nh, re.I) else None,
        )
        for h, nh in zip(headers, norm_headers, strict=False)
    ]
    mapping = FieldMapping(
        schema_version="1.0.0", connector_id="file_upload", doc_type=doc_type, rules=rules
    )
    entity_map = entity_map or DEFAULT_ENTITY_MAP
    seen: set[str] = set()
    out: list[CanonicalDocument] = []
    for row in rows:
        if not any(v not in (None, "") for v in row.values()):
            continue
        cd = apply_field_mapping(row, mapping)
        fields = {k: _coerce_value(k, v) for k, v in cd.fields.items()}
        # L3 实体归一
        for f in list(fields.keys()):
            if isinstance(fields[f], str) and fields[f] in entity_map:
                fields[f] = entity_map[fields[f]]
        h = _content_hash(fields)
        if h in seen:
            continue
        seen.add(h)
        out.append(
            CanonicalDocument(doc_type=doc_type, title=cd.title, fields=fields, content_hash=h)
        )
    return out


def normalize_text_block(text: str) -> str:
    """L2/L3 文本清洗：去零宽字符、合并连续空行、去除连续重复行。"""
    if not text:
        return ""
    text = text.replace("​", "").replace("﻿", "")
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")]
    collapsed: list[str] = []
    prev_blank = False
    for ln in lines:
        if ln == "":
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        collapsed.append(ln)
    deduped: list[str] = []
    last: str | None = None
    for ln in collapsed:
        if ln != "" and ln == last:
            continue
        deduped.append(ln)
        last = ln if ln != "" else last
    return "\n".join(deduped).strip()


__all__ = [
    "DEFAULT_ALIASES",
    "DEFAULT_ENTITY_MAP",
    "apply_aliases",
    "normalize_table_rows",
    "normalize_text_block",
]
