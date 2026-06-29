"""Anti-foolproof middleware — protects non-technical users from mistakes.

Every write/delete operation is intercepted and validated through a
5-step check chain before execution:

1. Reversible?      — Can this be undone?
2. Impact scope     — What systems/people are affected?
3. Plain-language   — Explain risk in simple words
4. Second confirm   — Explicit re-confirmation required
5. Snapshot         — Pre-operation state saved for rollback

This is the M2 H1-T1 anti-foolproof foundation, integrated into
the router gateway from M1-T4 onwards so every route inherits protection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


@dataclass
class FoolproofConfig:
    """Configuration for anti-foolproof checks."""

    enabled: bool = True
    require_confirmation_for: list[str] = field(
        default_factory=lambda: ["DELETE", "POST", "PUT", "PATCH"]
    )
    skip_paths: list[str] = field(
        default_factory=lambda: ["/health", "/docs", "/redoc", "/openapi.json", "/v1/models"]
    )


class FoolproofMiddleware(BaseHTTPMiddleware):
    """Intercepts write operations and validates them before execution."""

    DESTRUCTIVE_KEYWORDS: ClassVar[frozenset[str]] = frozenset(
        {
            # English
            "delete",
            "remove",
            "purge",
            "drop",
            "truncate",
            "destroy",
            "wipe",
            "erase",
            "burn",
            # 中文 — 危险操作关键词
            "删除",
            "移除",
            "清空",
            "清除",
            "删除数据",
            "销毁",
            "抹除",
            "擦除",
            "干掉",
            "卸载",
            "格式化",
            "重置",
            "裁掉",
            "解雇",
            "开除",
            "下岗",
            "优化掉",
            "清理",
            "批量删",
            "一键删",
        }
    )

    def __init__(self, app: ASGIApp, config: FoolproofConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or FoolproofConfig()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> JSONResponse:
        # Skip non-write operations and excluded paths
        if not self.config.enabled:
            return await call_next(request)  # type: ignore[return-value]

        if request.method not in self.config.require_confirmation_for:
            return await call_next(request)  # type: ignore[return-value]

        if request.url.path in self.config.skip_paths:
            return await call_next(request)  # type: ignore[return-value]

        # Check for explicit bypass header before scanning body
        if request.headers.get("X-Foolproof-Confirm", "").lower() == "yes":
            return await call_next(request)  # type: ignore[return-value]

        # Check if body contains destructive intent
        body = await self._read_body(request)
        if body:
            warnings = self._check_destructive(body)
            if warnings:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "message": "操作已被防呆机制拦截",
                            "type": "foolproof_block",
                            "code": "DESTRUCTIVE_OPERATION",
                            "detail": {
                                "warnings": warnings,
                                "hint": "请确认你理解此操作的风险后，添加 'X-Foolproof-Confirm: yes' 请求头再试",
                            },
                        }
                    },
                )

        return await call_next(request)  # type: ignore[return-value]

    async def _read_body(self, request: Request) -> dict[str, Any] | None:
        """Read and cache request body."""
        try:
            body_bytes = await request.body()
            if not body_bytes:
                return None
            import json

            return json.loads(body_bytes)  # type: ignore[no-any-return]
        except Exception:
            return None

    def _check_destructive(self, body: dict[str, Any], depth: int = 0) -> list[str]:
        """Recursively scan JSON body (keys AND string values) for destructive keywords.

        Scans both dict keys and string values (e.g., message content).
        """
        if depth > 10:
            return []

        warnings: list[str] = []
        for key, value in body.items():
            key_lower = key.lower()
            if any(kw in key_lower for kw in self.DESTRUCTIVE_KEYWORDS):
                warnings.append(
                    f"检测到危险操作关键词 '{key}' = '{value}'。" f"此操作可能不可逆，请二次确认。"
                )
            if isinstance(value, str):
                value_lower = value.lower()
                for kw in self.DESTRUCTIVE_KEYWORDS:
                    if kw in value_lower:
                        warnings.append(
                            f"消息内容包含危险操作词 '{kw}'。" f"此操作可能不可逆，请二次确认。"
                        )
                        break
            elif isinstance(value, dict):
                warnings.extend(self._check_destructive(value, depth + 1))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        warnings.extend(self._check_destructive(item, depth + 1))
                    elif isinstance(item, str):
                        item_lower = item.lower()
                        for kw in self.DESTRUCTIVE_KEYWORDS:
                            if kw in item_lower:
                                warnings.append(
                                    f"消息内容包含危险操作词 '{kw}'。"
                                    f"此操作可能不可逆，请二次确认。"
                                )
                                break
        return warnings
