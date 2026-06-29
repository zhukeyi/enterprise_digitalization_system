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
import time

from fastapi import FastAPI, HTTPException
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TracingMiddleware)

foolproof_config = FoolproofConfig(
    enabled=True, require_confirmation_for=["POST", "PUT", "PATCH", "DELETE"]
)
app.add_middleware(FoolproofMiddleware, config=foolproof_config)

# ── Services (eagerly initialized for testability) ───────────────────

model_registry = ModelRegistry()
model_registry.discover_adapters()
routing_engine = RoutingEngine()
fallback_chain = FallbackChain(model_registry)

logger = logging.getLogger("fde.router")
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
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse | JSONResponse:
    """Chat completions endpoint (OpenAI-compatible).

    Flow:
        1. Routing engine selects best model adapter
        2. Fallback chain ensures high availability
        3. Anti-foolproof checks warn on destructive prompts
    """
    start_time = time.monotonic()
    trace_id = _get_trace_id()

    # Log incoming request (mask sensitive fields in production)
    logger.info(
        "chat_completion trace=%s model=%s messages=%d max_tokens=%d",
        trace_id,
        request.model,
        len(request.messages),
        request.max_tokens or 0,
    )

    try:
        # Step 1: Route to best model
        selected_model = request.model or routing_engine.route(request)
        logger.info("trace=%s routed_to=%s", trace_id, selected_model)

        # Step 2: Execute with fallback
        response = await fallback_chain.execute(
            model_name=selected_model,
            request=request,
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


def _get_trace_id() -> str:
    """Get trace ID from context or generate new one."""
    import uuid

    return str(uuid.uuid4())


# Debug entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agents.router_agent.main:app", host="0.0.0.0", port=8080, reload=True)
