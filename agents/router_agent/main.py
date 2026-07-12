"""Router Agent — Unified API Gateway (FastAPI).

OpenAI-compatible entry point with pluggable model adapters,
intelligent routing strategy, and automatic failover.

M1-T4: FastAPI gateway + anti-foolproof middleware
M1-T5: Multi-model adapters (Mock + DeepSeek/Qwen/GLM)
M1-T6: Routing strategy engine (YAML-configured)
M1-T7: Failover chain (automatic switch within 3s)
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents.router_agent.adapters import ModelRegistry
from agents.router_agent.middleware.anti_foolproof import FoolproofConfig, FoolproofMiddleware
from agents.router_agent.middleware.tracing import TracingMiddleware
from agents.router_agent.models.request import ChatCompletionRequest
from agents.router_agent.models.response import (
    ChatCompletionResponse,
    ErrorResponse,
    ModelListResponse,
)
from agents.router_agent.routing.engine import RoutingEngine
from agents.router_agent.routing.fallback import FallbackChain
from shared.models import HealthResponse

# ── App Setup ───────────────────────────────────────────────────────

logger = logging.getLogger("fde.router")

app = FastAPI(
    title="FDE Router Agent",
    description="Unified AI gateway — OpenAI-compatible /v1/chat/completions",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ──────────────────────────────────────────────────────

# ── CORS — configurable via env ───────────────────────────────

_cors_origins = os.getenv("FDE_CORS_ORIGINS", "*")
if _cors_origins == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    allowed = [o.strip() for o in _cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(TracingMiddleware)

foolproof_config = FoolproofConfig(
    enabled=True, require_confirmation_for=["POST", "PUT", "PATCH", "DELETE"]
)
app.add_middleware(FoolproofMiddleware, config=foolproof_config)

# ── Auth Middleware (M2-T1) ─────────────────────────────────────

ENABLE_AUTH = os.getenv("FDE_ENABLE_AUTH", "").lower() in ("1", "true", "yes")

if ENABLE_AUTH:
    try:
        from agents.governance_agent.auth.router import router as auth_router
        from agents.governance_agent.middleware import AuthMiddleware

        app.add_middleware(
            AuthMiddleware,
            public_paths=[
                "/health",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/auth/login",
                "/auth/register",
                "/auth/refresh",
            ],
        )
        app.include_router(auth_router)
        logger.info("AuthMiddleware and auth router registered (M2-T1)")
    except ImportError:
        logger.warning("Governance Agent dependencies not available — auth disabled")
else:
    logger.info("Auth middleware disabled (set FDE_ENABLE_AUTH=1 to enable)")

# ── MapAI Router (Module L) ─────────────────────────────────────

try:
    from agents.map_agent import map_router

    app.include_router(map_router)
    logger.info("MapAI router registered at /map/*")
except ImportError:
    logger.warning("MapAI dependencies not available — /map endpoints disabled")

# ── Ingestion Router (P2a / MVS) ──────────────────────────────

try:
    from agents.ingestion_agent.router import router as ingestion_router

    app.include_router(ingestion_router)
    logger.info("Ingestion router registered (/ingest/upload, /api/data/ask)")
except ImportError:
    logger.warning("Ingestion agent unavailable — /ingest endpoints disabled")

# ── Intelligence Router (V5-④ 情报增幅器) ─────────────────────

try:
    from agents.data_agent.router import router as data_router

    app.include_router(data_router)
    logger.info("Intelligence router registered at /api/intelligence/*")
except ImportError:
    logger.warning("Data agent router unavailable — /api/intelligence endpoints disabled")

# ── HR Router (V5-⑥ HR 智能评估) ─────────────────────────────

try:
    from agents.hr_agent.router import router as hr_router

    app.include_router(hr_router)
    logger.info("HR router registered at /api/hr/*")
except ImportError:
    logger.warning("HR agent router unavailable — /api/hr endpoints disabled")

# ── Pricing Router (V5-⑦ 动态定价引擎) ───────────────────────

try:
    from agents.pricing_agent.router import router as pricing_router

    app.include_router(pricing_router)
    logger.info("Pricing router registered at /api/pricing/*")
except ImportError:
    logger.warning("Pricing agent router unavailable — /api/pricing endpoints disabled")

# ── Marketing Router (V5-⑤ GEO / 广告 / 内容 / 分析) ──────────

try:
    from agents.marketing_agent.router import router as marketing_router

    app.include_router(marketing_router)
    logger.info("Marketing router registered at /api/marketing/*")
except ImportError:
    logger.warning("Marketing agent router unavailable — /api/marketing endpoints disabled")

# ── Dify OpenAPI spec endpoint (P7: Dify Custom Tool import) ────


@app.get("/dify/openapi.yaml")
async def dify_openapi_spec():
    """Serve the FDE OpenAPI 3.0 spec for Dify custom tool import.

    In Dify: 工具 → 创建自定义工具 → OpenAPI → 输入 URL:
    https://host:8443/fde-api/dify/openapi.yaml
    """
    from pathlib import Path

    spec_path = Path(__file__).resolve().parent.parent.parent / "docs" / "fde-dify-openapi.yaml"
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(spec_path.read_text(encoding="utf-8"), media_type="text/yaml")


# ── Startup — database initialization ───────────────────────────


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize database, migrations, and P6a worker on first start."""
    try:
        from agents.governance_agent.database.session import (
            get_engine,
            init_database,
        )

        await init_database()
        logger.info("Database tables initialized")
        # P3b/P6a 迁移：补齐新列 + FTS + ingest_tasks（幂等）
        try:
            from agents.ingestion_agent.migration import migrate_schema

            await migrate_schema(get_engine())
            logger.info("P3b/P6a schema migration applied")
        except Exception as e:
            logger.warning("Migration skipped/failed (non-fatal): %s", e)

        # P6a: start async ingestion worker
        try:
            from agents.governance_agent.database.session import _get_session_factory
            from agents.ingestion_agent.storage import get_storage
            from agents.ingestion_agent.store import get_embedding_model, get_vector_store
            from agents.ingestion_agent.tasks import start_worker

            _ = await start_worker(
                session_factory=_get_session_factory(),
                vector_store=get_vector_store(),
                embedding_model=get_embedding_model(),
                object_storage=get_storage(),
            )
            logger.info("P6a IngestWorker started")
        except Exception as e:
            logger.warning("P6a worker start failed (non-fatal): %s", e)
    except ImportError:
        logger.debug("Database not configured, skipping init")
    except Exception as e:
        logger.warning("Database init failed (may be expected in dev): %s", e)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Gracefully stop the P6a worker."""
    try:
        from agents.ingestion_agent.tasks import stop_worker

        await stop_worker()
        logger.info("P6a IngestWorker stopped")
    except ImportError:
        pass


# ── Services (eagerly initialized for testability) ───────────────────

model_registry = ModelRegistry()
model_registry.discover_adapters()
routing_engine = RoutingEngine()
fallback_chain = FallbackChain(model_registry)

logger.info("Router Agent loaded with %d adapters", len(model_registry.list_models()))


# ═══════════════════════════════════════════════════════════════════════
# OpenAI-Compatible Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check."""
    components = dict.fromkeys(model_registry.list_models(), "ok")
    return HealthResponse(components=components)


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """List available models (OpenAI-compatible)."""
    models = model_registry.list_models()
    return ModelListResponse(
        object="list",
        data=[{"id": m, "object": "model", "created": 0, "owned_by": "fde"} for m in models],
    )


@app.post("/v1/chat/completions", response_model=None, responses={400: {"model": ErrorResponse}})
async def chat_completions(
    request: Request, chat_request: ChatCompletionRequest
) -> ChatCompletionResponse | JSONResponse:
    """Chat completions endpoint (OpenAI-compatible).

    Flow:
        1. Routing engine selects best model adapter
        2. Fallback chain ensures high availability
        3. Anti-foolproof checks warn on destructive prompts
    """
    start_time = time.monotonic()
    trace_id = _get_trace_id(request)

    # Log incoming request (mask sensitive fields in production)
    logger.info(
        "chat_completion trace=%s model=%s messages=%d max_tokens=%d",
        trace_id,
        chat_request.model,
        len(chat_request.messages),
        chat_request.max_tokens or 0,
    )

    try:
        # Step 1: Route to best model
        selected_model = chat_request.model or routing_engine.route(chat_request)
        logger.info("trace=%s routed_to=%s", trace_id, selected_model)

        # Step 2: Execute with fallback
        response = await fallback_chain.execute(
            model_name=selected_model,
            request=chat_request,
            trace_id=trace_id,
        )

        elapsed = (time.monotonic() - start_time) * 1000
        logger.info("trace=%s completed model=%s latency=%.1fms", trace_id, response.model, elapsed)
        return response

    except ValueError as e:
        logger.warning("trace=%s routing_error: %s", trace_id, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("trace=%s unexpected_error: %s", trace_id, e)
        raise HTTPException(status_code=500, detail="Internal router error") from e


# ═══════════════════════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════════════════════


def _get_trace_id(request: Request) -> str:
    """Get trace ID from TracingMiddleware state or generate new one."""
    try:
        return request.state.trace_id
    except (AttributeError, KeyError):
        import uuid

        return str(uuid.uuid4())


# Debug entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agents.router_agent.main:app", host="0.0.0.0", port=8080, reload=True)
