# FDE AI Platform - Environment Audit Report

> Generated: 2026-07-14
> Scope: Local dev (macOS ARM) + Production server (Oracle ARM 217.142.246.70)

---

## 1. Local Development Environment (macOS)

### 1.1 Python Runtimes

| Runtime | Version | Path | Role |
|---------|---------|------|------|
| Managed (primary) | 3.13.12 | `~/.workbuddy/binaries/python/versions/3.13.12/` | WorkBuddy default |
| Homebrew (system) | 3.13.3 | `/opt/homebrew/bin/python3` | Fallback only |
| System | 3.x | `/usr/bin/python3` | macOS built-in, unused |

### 1.2 Python Virtual Environments

| venv | Path | Python | Packages | Purpose |
|------|------|--------|----------|---------|
| **default** | `~/.workbuddy/binaries/python/envs/default/` | 3.13.12 | ~50 | General-purpose: ruff, black, mypy, pytest, fastapi, httpx, numpy, scipy, torch |
| **fde-test** | `~/.workbuddy/binaries/python/envs/fde-test/` | 3.13.12 | ~40 | FDE integration tests: langgraph, aiohttp, fastapi 0.139 |
| **fde-docling** | `~/.workbuddy/binaries/python/envs/fde-docling/` | 3.13.12 | ~60 | Docling parser: docling 2.112, torch 2.13, opencv, transformers |
| **xr_research** | `~/.workbuddy/binaries/python/envs/xr_research/` | 3.13.12 | ~30 | Unrelated research project (beautifulsoup, folium) |
| **.venv (project)** | `fde-ai-platform/.venv/` | 3.13.12 | 129 | FDE main dev: fastapi, qdrant-client, numpy, ruff, mypy, pytest |

### 1.3 Node.js Runtimes

| Runtime | Version | Path |
|---------|---------|------|
| Managed (primary) | 22.22.2 | `~/.workbuddy/binaries/node/versions/22.22.2/` |
| Managed (alt) | 20.18.0 | `~/.workbuddy/binaries/node/versions/20.18.0/` |

| Workspace | Path | Packages |
|-----------|------|----------|
| Node workspace | `~/.workbuddy/binaries/node/workspace/` | 46 (axios, etc.) |

### 1.4 Frontend Portals (9 projects, each has own node_modules)

| Portal | Path | Status |
|--------|------|--------|
| portal | `frontend/portal/` | Active |
| intelligence-portal | `frontend/intelligence-portal/` | Active |
| marketing-portal | `frontend/marketing-portal/` | Active |
| hr-portal | `frontend/hr-portal/` | Active |
| pricing-portal | `frontend/pricing-portal/` | Active |
| observability-portal | `frontend/observability-portal/` | Active |
| hub | `frontend/hub/` | Active |
| training-portal | `frontend/training-portal/` | Active |
| map-ai | `frontend/map-ai/` | Frozen (archived) |

All are Vue 3 + Vite + ECharts. Each has its own `node_modules/` (not shared, not hoisted).

### 1.5 Local Tools

| Tool | Location | Notes |
|------|----------|-------|
| Docker | `/usr/local/bin/docker` (29.2.1) | Installed but NO containers/images running locally |
| Ollama | `/usr/local/bin/ollama` | 3 models: qwen2.5:7b (4.7G), qwen3-vl:8b (6.1G), nomic-embed-text (274M) |
| Git | system | Repo at `fde-ai-platform/` |
| ruff/black/mypy | in `.venv` and `default` env | Duplicated (see issues below) |

### 1.6 Code Quality Tools (pyproject.toml config)

| Tool | Config | Target |
|------|--------|--------|
| ruff | `[tool.ruff]` line-length=100, py311 | Linting + formatting |
| black | `[tool.black]` line-length=100, py311 | Formatting (may conflict with ruff format) |
| mypy | `[tool.mypy]` python_version=3.11 | Type checking (strict) |
| pytest | `[tool.pytest]` asyncio=auto | Testing + coverage |

---

## 2. Production Server (Oracle ARM 217.142.246.70)

### 2.1 Host Specs

| Spec | Value |
|------|-------|
| OS | Ubuntu 24.04 LTS (aarch64) |
| Kernel | 6.17.0-1011-oracle |
| CPU | 2 cores (ARM) |
| RAM | 11.6 GB total, 4.5 GB used, 7.4 GB available |
| Disk | 96 GB, 43 GB used (45%), 54 GB free |
| Swap | 0 (none configured) |

### 2.2 Service Architecture

```
Internet (HTTPS:443)
    |
    v
Nginx (systemd, :8443 SSL self-signed)
    |--- /fde-api/     -> 127.0.0.1:8000 (FDE Backend)
    |--- /fde/         -> /var/www/html (portal dist)
    |--- /portal/      -> /var/www/ (portal dist)
    |--- /intel/       -> /var/www/ (intel dist)
    |--- /marketing/   -> /var/www/marketing-portal
    |--- /hr/          -> /var/www/ (hr dist)
    |--- /pricing/     -> /var/www/ (pricing dist)
    |--- /hub/         -> /var/www/ (hub dist)
    |--- /training/    -> /var/www/ (training dist)
    |--- /obs/         -> /var/www/ (obs dist)
    |--- / (root)      -> 172.18.0.12:80 (Dify via Docker nginx)
    |--- /console/api  -> 172.18.0.12:80 (Dify API)
    |--- /api          -> 172.18.0.12:80 (Dify API)
    |--- /v1           -> 172.18.0.12:80 (Dify)
    |--- /socket.io/   -> 172.18.0.12:80 (Dify WS)
```

### 2.3 FDE Backend (systemd service)

| Property | Value |
|----------|-------|
| Service | `fde-backend.service` |
| Status | Active (running) |
| WorkingDirectory | `/home/ubuntu/fde-ai-platform` |
| ExecStart | `venv/bin/python -m uvicorn agents.router_agent.main:app --host 0.0.0.0 --port 8000` |
| Restart | always (RestartSec=5) |
| Env | `PYTHONUNBUFFERED=1`, `FDE_RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5` |
| venv Python | 3.12.3 (system /usr/bin/python3) |
| Health | OK (all 9 model adapters reporting ok) |

### 2.4 Server venv Key Packages

| Package | Version | Notes |
|---------|---------|-------|
| fastapi | 0.138.2 | |
| pydantic | 2.13.4 | |
| qdrant-client | 1.18.0 | |
| httpx | 0.28.1 | |
| numpy | 2.5.1 | |
| scipy | 1.18.0 | |
| onnxruntime | 1.27.0 | BGE embedding backend |
| pdfplumber | 0.11.10 | PDF parsing |
| jieba | 0.42.1 | Chinese tokenization |
| langgraph | 1.2.7 | Orchestrator |
| aiohttp | 3.14.1 | map_agent |
| torch | 2.13.0 | Installed (possibly unused overhead) |
| uvicorn | 0.49.0 | ASGI server |

**Missing on server (present locally):** ruff, black, mypy, pytest (dev-only tools, not needed in production).

### 2.5 Docker Containers (15 running)

| Container | Image | Status | Port | Purpose |
|-----------|-------|--------|------|---------|
| fde-litellm | litellm:main-latest (1.93.0) | Up 29h (**unhealthy**) | :4000 (host net) | LLM proxy |
| docker-nginx-1 | nginx:latest | Up 10d | :80, :443 | Dify reverse proxy |
| docker-api-1 | dify-api:1.15.0 | Up 10d (healthy) | 5001 | Dify API |
| docker-worker-1 | dify-api:1.15.0 | Up 10d | 5001 | Dify worker |
| docker-worker_beat-1 | dify-api:1.15.0 | Up 10d | 5001 | Dify celery beat |
| docker-api_websocket-1 | dify-api:1.15.0 | Up 10d | 5001 | Dify WS |
| docker-plugin_daemon-1 | dify-plugin-daemon:0.6.3 | Up 10d | :5003 | Dify plugins |
| docker-web-1 | dify-web:1.15.0 | Up 10d | 3000 | Dify frontend |
| docker-db_postgres-1 | postgres:15-alpine | Up 10d (healthy) | 5432 | Dify DB |
| docker-redis-1 | redis:6-alpine | Up 10d (healthy) | 6379 | Dify cache |
| docker-sandbox-1 | dify-sandbox:0.2.15 | Up 10d (healthy) | - | Dify sandbox |
| docker-ssrf_proxy-1 | squid:latest | Up 2d | 3128 | Dify SSRF proxy |
| docker-weaviate-1 | weaviate:1.27.0 | Up 10d | - | Dify vector DB |
| qdrant | qdrant:v1.13.2 | Up 2w | :6333-6334 | FDE vector DB |

### 2.6 Host-Level Services

| Service | Status | Port | Notes |
|---------|--------|------|-------|
| nginx | systemd active | :8443 SSL | FDE reverse proxy |
| fde-backend | systemd active | :8000 | FastAPI/uvicorn |
| postgresql | systemd active | :127.0.0.1:5432 | PostgreSQL 16.14 (LiteLLM keys only) |
| Ollama | NOT installed | - | Local only (dev) |

### 2.7 Docker Data

| Path | Size |
|------|------|
| `/var/lib/docker` | 18 GB |
| `/home/ubuntu/fde-ai-platform` | 7.1 GB |
| `/var/www` | 1.3 MB |

### 2.8 Docker Compose Files on Server

| Path | Purpose |
|------|---------|
| `fde-ai-platform/deploy/docker-compose.prod.yml` | FDE prod (not currently used — services run via systemd) |
| `fde-ai-platform/docker-compose.dev.yml` | FDE dev (not used on server) |
| `enterprise-connector/docker-compose.yml` | Logistics connector |
| `video-connector/docker-compose.yml` | Video connector |

### 2.9 NOT Deployed Yet (P1-A New)

| Component | Status |
|-----------|--------|
| RSSHub (:1200) | Docker compose ready locally, NOT deployed to server |
| crawl4ai | Code ready, NOT deployed (env var not set on server) |
| RSSHub Redis | Same as above |

---

## 3. Issues Found

### 3.1 Redundant Python Environments

**Issue**: 5 Python venvs exist, with significant package overlap.

| Package | .venv | default | fde-test | fde-docling |
|---------|-------|---------|----------|-------------|
| fastapi | 0.138.1 | 0.138.0 | 0.139.0 | - |
| pydantic | 2.13.4 | 2.13.4 | 2.13.4 | - |
| httpx | 0.28.1 | 0.28.1 | 0.28.1 | - |
| numpy | 2.5.1 | 2.4.6 | 2.5.1 | - |
| pytest | 9.1.1 | 9.1.1 | 9.1.1 | - |
| ruff | 0.15.20 | 0.15.20 | 0.15.21 | - |

**Root cause**: `.venv` was created for the FDE project; `default` is WorkBuddy's general env; `fde-test` was created when `.venv` lacked langgraph/aiohttp; `fde-docling` was isolated to avoid torch pollution.

**Recommendation**: Consolidate to 2 venvs:
1. `.venv` (project) — add langgraph + aiohttp, make it the single FDE dev env
2. `fde-docling` — keep isolated (torch is heavy, optional dependency)
3. Deprecate `default` and `fde-test` for FDE work

### 3.2 ruff + black Coexistence

**Issue**: `pyproject.toml` configures both `[tool.ruff]` (with `[tool.ruff.format]`) and `[tool.black]`. Both are formatters with the same line-length=100.

**Risk**: If both run, they may fight over formatting style (ruff format vs black produce slightly different output).

**Recommendation**: Choose one. ruff format is recommended (replaces black + isort + flake8 in one tool). Remove `[tool.black]` section.

### 3.3 Server: torch Installed but Likely Unnecessary

**Issue**: Server venv has `torch 2.13.0` installed (~2GB). The FDE backend uses ONNX runtime for embeddings, not torch directly. Docling (which needs torch) is configured with `FDE_PARSER_BACKEND=auto` and falls back to pdfplumber.

**Risk**: Wastes ~2GB disk and increases memory pressure.

**Recommendation**: Verify if any server code path actually imports torch. If not, `pip uninstall torch torchvision` to save 2GB.

### 3.4 Server: LiteLLM Health Check Failing

**Issue**: `fde-litellm` container shows status "unhealthy" despite `curl localhost:4000/health/liveliness` returning "I'm alive!".

**Root cause**: The Docker healthcheck uses `curl -f http://localhost:4000/health/liveliness` but the container uses `network_mode: host`, so localhost should work. The "unhealthy" status may be a transient issue or the health check command (`curl`) may not be available in the LiteLLM image.

**Recommendation**: Change healthcheck to use `wget` or install curl in the image. Or use `CMD-SHELL` with a Python one-liner.

### 3.5 Server: No Swap Configured

**Issue**: `Swap: 0 0 0` — no swap space on an 11GB machine running 15 Docker containers.

**Risk**: Memory spikes (especially from Dify + LiteLLM + Qdrant) could trigger OOM kills.

**Recommendation**: Add 4GB swap file:
```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3.6 P1-A Components Not Yet Deployed

**Issue**: RSSHub (:1200) and crawl4ai are coded and tested locally but NOT deployed to the server. The server has no `deploy/rsshub/` directory.

**Recommendation**: Deploy RSSHub when ready:
```bash
scp -r deploy/rsshub/ ubuntu@217.142.246.70:~/fde-ai-platform/deploy/
ssh ubuntu@217.142.246.70 "cd ~/fde-ai-platform/deploy/rsshub && docker compose up -d"
```

### 3.7 Stale Qdrant Image

**Issue**: Two Qdrant images exist on server: `v1.13.2` (running) and `v1.7.4` (dangling, 246MB). The running container uses v1.13.2 which is correct, but the old image wastes disk.

**Recommendation**: `docker image prune` to remove dangling images.

### 3.8 Frontend node_modules Duplication

**Issue**: 9 frontend portals each have their own `node_modules/`. No workspace hoisting (pnpm/npm workspaces) is configured.

**Impact**: ~9x duplicate Vue/Vite/ECharts installations. Estimated 2-3 GB total.

**Recommendation**: If disk is not a concern locally, leave as-is. If it is, consider npm/pnpm workspaces with hoisted dependencies. Low priority.

### 3.9 xr_research Environment (Unrelated)

**Issue**: `~/.workbuddy/binaries/python/envs/xr_research/` contains packages from a different project (beautifulsoup, folium). Not used by FDE.

**Recommendation**: No action needed. Just be aware it's not an FDE env.

---

## 4. Summary Matrix

| Dimension | Local (macOS) | Server (Oracle ARM) |
|-----------|---------------|---------------------|
| **Python** | 3.13.12 (managed) + 3.13.3 (homebrew) | 3.12.3 (system) |
| **venvs** | 5 (.venv, default, fde-test, fde-docling, xr_research) | 1 (venv) |
| **Node** | 22.22.2 + 20.18.0 (managed) | N/A (frontend built locally, deployed as static) |
| **Frontend** | 9 portals with node_modules | Static dist in /var/www/ |
| **Docker** | Installed, 0 containers | 15 containers (Dify stack + Qdrant + LiteLLM) |
| **Ollama** | Installed (3 models, 11GB) | Not installed |
| **LiteLLM** | Config in repo, not running | Running :4000 (unhealthy flag) |
| **Qdrant** | Not running | Running :6333 (v1.13.2) |
| **Postgres** | Not installed | 16.14 (systemd, LiteLLM keys only) |
| **Nginx** | Not running | systemd, :8443 SSL self-signed |
| **RSSHub** | Code ready, not running | Not deployed yet |
| **crawl4ai** | Code ready (fallback mode) | Not deployed yet |
| **Code quality** | ruff + black + mypy in .venv | Not installed (prod) |
| **Disk** | N/A | 43G/96G used (45%) |
| **Memory** | N/A | 4.5G/11.6G used (39%) |
