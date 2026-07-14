# FDE AI Platform - Enterprise Informatization Training Manual

> Companion to V5 "Enterprise Landing Seven-Step Method" Module 3 (Training & Certification).
> This manual covers all seven modules and the three-tier certification system (Operator / Analyst / Architect).

---

## 0. Platform Overview

FDE AI Platform is an "AI Landing Operating System" for enterprises. It converts large-model capabilities into operable business modules through the Seven-Step Method:

| Step | Module | One-Line Value | Portal Path |
|------|--------|---------------|-------------|
| 1 | Foundation | Knowledge ingestion + unified retrieval base | `/portal/` |
| 2 | Delivery | Custom dashboard - turn data into executive-readable views | `/portal/dashboard` |
| 3 | Training | This module - make people proficient and productive | `/hub/` |
| 4 | Intelligence | External intelligence amplifier - monitor competitors & industry | `/intel/` |
| 5 | Marketing | GEO投放 - get AI search engines to recommend you | `/marketing/` |
| 6 | Downsizing | Intelligent redundancy assessment (with foolproof safeguards) | `/hr/` |
| 7 | Pricing | Dynamic pricing engine - elasticity & competitor-driven pricing | `/pricing/` |

Unified entry: `/hub/` (Seven-Step navigation page).

### 0.1 System Architecture (Cheat Sheet)

```
User Browser
    |
    v
Nginx (port 443/8443)
    |--- /fde/        -> Frontend portal (dist)
    |--- /fde-api/    -> FastAPI backend (port 8000)
    |--- /portal/     -> MVS portal
    |--- /intel/      -> Intelligence portal
    |--- /marketing/  -> Marketing portal
    |--- /hr/         -> HR portal
    |--- /pricing/    -> Pricing portal
    |--- /hub/        -> Unified navigation
    |--- /obs/        -> Observability platform
    |--- /training/   -> Training portal
    |
    v
FastAPI Backend (port 8000)
    |--- 16 Agent modules
    |--- LiteLLM Proxy (port 4000) -> DeepSeek / GLM / Qwen
    |--- Qdrant (port 6333) - Vector database
    |--- RSSHub (port 1200) - Self-hosted RSS feeds
    |--- Dify - LLM workflow orchestration
```

### 0.2 Supported Data Source Types

| Type | Enum | Use Case |
|------|------|----------|
| Web Page | `web` | Direct HTTP fetch + HTML parsing |
| RSS/Atom | `rss` | Standard RSS/Atom feed subscription |
| REST API | `api` | JSON REST API endpoints |
| Customs | `customs` | Trade customs data (UN Comtrade / BOL) |
| RSSHub | `rsshub` | Self-hosted RSSHub (1000+ routes) |
| crawl4ai | `crawl4ai` | Deep web crawl, LLM-ready Markdown output |

---

## 1. Operator Certification (Level 1)

**Goal**: Complete daily operations under guidance without crossing red lines.

**Exam**: 60 minutes - theory + practical.

### 1.1 Knowledge Ingestion

**Portal**: `/portal/` -> "Upload" page.

**Supported formats**: xlsx, csv, pdf, docx, pptx.

**Pipeline**: Upload -> Parse (pdfplumber/Docling) -> Normalize -> Chunk -> Embed (BGE ONNX) -> Store (Qdrant).

**Mnemonic**: **Structure first, ingest second, query third.**

**Steps**:
1. Log in to `/portal/`
2. Navigate to "Upload" page
3. Drag-and-drop or browse to select a file
4. Wait for "Ingestion complete" notification
5. Go to "Chat" page and ask questions in natural language

### 1.2 Dashboard Viewing

**Portal**: `/portal/dashboard`

- Views enterprise core metric panels.
- Dashboard metrics refresh from the data access layer in real-time.
- Anomalies are auto-highlighted in red.

### 1.3 Intelligence Subscription

**Portal**: `/intel/`

- "Sources" page: Add RSS / HTTP / API / RSSHub sources.
- "Alerts" page: Set keywords (competitor names, regulatory terms). System generates trigger records on keyword match.
- "Trends" page: View 14-day collection curve and keyword cloud.
- "Reports" page: One-click export of Markdown briefings.

### 1.4 Red Lines (Exam-Critical)

| # | Rule | Rationale |
|---|------|-----------|
| R1 | Do NOT upload files containing personal sensitive info (ID numbers, bank cards) | Data security law compliance |
| R2 | Do NOT bypass foolproof dialogs to directly execute downsizing plans | irreversible personnel decisions require multi-step approval |
| R3 | Pricing suggestions are advisory only; final prices require human approval | algorithmic pricing can be wrong |
| R4 | Do NOT share API keys or tenant credentials | multi-tenant isolation |
| R5 | Do NOT disable audit logging | all key operations must be traceable |

### 1.5 Daily Checklist (Operator)

- [ ] Check `/obs/` health dashboard for anomalies
- [ ] Review intelligence alerts from last 24h
- [ ] Confirm dashboard metrics are refreshing
- [ ] Verify no upload errors in ingestion queue
- [ ] Log out when leaving workstation

---

## 2. Analyst Certification (Level 2)

**Goal**: Independently configure modules, interpret results, and provide business recommendations.

**Exam**: 90 minutes - theory + practical + case analysis.

### 2.1 GEO Marketing

**Portal**: `/marketing/` (4 views)

| View | Purpose | Key Metrics |
|------|---------|-------------|
| GEO Dashboard | Brand visibility in AI search engines | GEO index, citation count |
| Content Studio | E-E-A-T optimized content generation | Content score, keyword coverage |
| Ad Management | A/B variant testing | CTR, significance p-value |
| ROI Dashboard | Campaign return analysis | ROAS, CPA, conversion funnel |

**Key Concepts**:
- **GEO Index**: Rate at which your brand is cited by AI search engines (ChatGPT, Perplexity, etc.)
- **ROAS**: Revenue divided by ad spend. ROAS > 3x is healthy.
- **E-E-A-T**: Experience, Expertise, Authoritativeness, Trustworthiness - Google's content quality framework.

**Practical Exercise**:
1. Use Content Studio to generate an E-E-A-T optimized article
2. Create 2 A/B variants in Ad Management
3. Read significance test results (p < 0.05 = significant)
4. Export ROI report

### 2.2 Dynamic Pricing

**Portal**: `/pricing/` (5 views)

| View | Purpose |
|------|---------|
| Overview | Current pricing strategy summary |
| What-if Simulator | Test different price scenarios |
| Strategy Optimizer | AI-driven price recommendations |
| Elasticity Analysis | Price elasticity coefficient per product |
| Competitor Monitor | Track competitor price changes |

**Key Concepts**:
- **Price Elasticity**: Percentage change in demand for 1% price change. Coefficient -1.5 means: raise price 1% -> demand drops 1.5%.
- **Optimal Price**: Where marginal revenue equals marginal cost. The platform calculates this via OLS regression.

**Practical Exercise**:
1. Read elasticity coefficient for a product in "Elasticity Analysis"
2. In "Simulator", test +5% price increase
3. Calculate: profit = (price * 1.05 - cost) * demand * (1 + 0.05 * elasticity)
4. Document the result and recommendation

### 2.3 Intelligence Deep Dive

**Portal**: `/intel/`

- Configure RSSHub routes for industry-specific feeds (see `/intel/` Sources page -> "RSSHub Predefined Routes")
- Use crawl4ai source type for deep web page extraction (LLM-ready Markdown)
- Set up multi-keyword alerts with sentiment filtering
- Export trend reports with date-range selection

### 2.4 Customs Trade Data (P1-C)

**Portal**: `/intel/` -> "Customs" view

- **Tier-1**: UN Comtrade (free, aggregated, official)
- **Tier-2**: BOL commercial data (granular, paid, requires compliance screening)
- Search by HS code, reporter country, partner country
- View buyer entity profiles (derived, zero raw PII)
- Export trade trend analysis

**Compliance Red Lines**:
- Only derived BuyerEntity data is exposed (zero raw BOL)
- OFAC/EU sanctions screening runs on every query
- Enterprise channel only (no consumer-facing push)

### 2.5 Analysis Output Standards

| Output Type | Format | Required Elements |
|-------------|--------|-------------------|
| Intelligence Brief | Markdown | Date range, source count, key findings, sentiment breakdown |
| Pricing Recommendation | PDF | Elasticity coefficient, scenario table, risk caveat |
| GEO Campaign Report | HTML | ROAS, A/B significance, content performance |
| Customs Trade Analysis | Excel | HS code, trend chart, buyer list, compliance note |

---

## 3. Architect Certification (Level 3)

**Goal**: Design landing solutions, configure Dify workflows, control compliance risks, and lead enterprise deployment.

**Exam**: 120 minutes - theory + scenario + system design.

### 3.1 Dify Workflow Orchestration

**Setup**:
1. Import `docs/fde-dify-openapi.yaml` as Custom Tool (provider: `fde_data_tool`)
2. Import preset workflows from `docs/dify-workflows/`:
   - Contract Analysis
   - Data Q&A
   - Intelligence Briefing
   - Pricing Recommendation
3. Combine FDE tool nodes with LLM nodes to build industry-specific flows

**Tenant Configuration**:
- Dify tenant ID: `d1927730-17df-435e-9e19-bd11c3a67bc1`
- Tool servers URL: `http://172.18.0.1:8000` (Docker bridge to host)

### 3.2 Downsizing Assessment (Foolproof Five Steps)

**Portal**: `/hr/simulator`

The system enforces a mandatory 5-step foolproof process:

| Step | Name | What Happens | Cannot Skip |
|------|------|-------------|-------------|
| 1 | Reversibility Check | System verifies if action is reversible | Yes |
| 2 | Impact Scope Assessment | Shows affected headcount, departments, cost | Yes |
| 3 | Plain-Language Explanation | Generates non-technical summary of consequences | Yes |
| 4 | Secondary Confirmation | User must type "confirm downsizing" | Yes |
| 5 | Snapshot Archive | Full plan saved to audit log | Yes |

**Architect-Level Requirements**:
- Must explain to management the legal basis for each step
- Must be able to interpret risk levels (Low/Medium/High) and their business implications
- Must understand that "High" risk means: potential public relations or legal cost may exceed savings

### 3.3 Source Expansion Configuration (P1-A)

**RSSHub Self-Hosting**:
- Deploy: `cd deploy/rsshub && docker compose up -d`
- Port: 1200 (no conflict with LiteLLM 4000, Qdrant 6333)
- Predefined routes: See `/intel/` -> Sources -> "RSSHub Predefined Routes"
- Custom routes: Add via API `POST /api/intelligence/collect` with `source_type=rsshub`

**crawl4ai Scraper**:
- Backend selection: `FDE_CRAWL4AI_BACKEND` env var (auto/crawl4ai/fallback)
- Resource assessment: See `docs/resource-assessment-p1a.md`
- Worker machine: If host memory > 70%, deploy separate crawl worker (see resource assessment doc)

### 3.4 Compliance & Audit

| Area | Requirement | Tool |
|------|-------------|------|
| Audit Log | All key operations written to immutable log | `/obs/` -> Audit Trail |
| PII Protection | No PII in vector store; uploads screened | Ingestion pipeline |
| Sanctions Screening | OFAC/EU check on all customs queries | `compliance_guard.py` |
| GEO Guard | Anti-pollution detection on intelligence data | `geo_guard.py` |
| Access Control | RBAC + ABAC + JWT/API Key | Auth middleware |

### 3.5 Deployment Architecture

```
Oracle ARM Host (2C/11G/96G)
  |
  +-- Nginx (443) -- SSL termination, static files, reverse proxy
  +-- FastAPI (8000) -- FDE backend, 16 agents
  +-- LiteLLM (4000) -- LLM proxy, virtual keys
  +-- Qdrant (6333) -- Vector database
  +-- RSSHub (1200) -- Self-hosted RSS feeds
  +-- Dify -- LLM workflow orchestration
  +-- Postgres 16 -- LiteLLM key storage only
```

**Key Constraints**:
- All numpy math modules must NOT depend on pandas/xgboost/prophet (not installed)
- Memory safety line: <= 70% of 11G = ~7.7 GB
- LiteLLM memory cap: 1.5 GB (512 MB causes OOM)
- crawl4ai concurrency: limit to 1 page (400 MB peak)

### 3.6 Observability Platform

**Portal**: `/obs/`

| View | Purpose |
|------|---------|
| Health Dashboard | System component status, uptime |
| Token Router | LLM token usage, cost tracking |
| RAG Inspector | Retrieval quality, chunk-level debugging |
| Trace Viewer | Request-level distributed tracing |
| Audit Trail | Immutable operation log, alert rules |
| Drift Detection | Model output drift monitoring |

---

## 4. Training Format

| Format | Content | Duration |
|--------|---------|----------|
| Online video | Module operation demos | 15 min per module |
| Live workshop | Real dataset exercises | 2h per session |
| Sandbox drill | Simulated downsizing / pricing decisions | Half day |
| Certification exam | Theory + practical + scenario | L1: 60min / L2: 90min / L3: 120min |

> Video scripts: See `video-scripts.md`. Exam bank: See `exam-bank.md`. Certification: See `certification.md`.

---

## 5. Quick Reference Card

### 5.1 Portal URLs

| Portal | Path | Primary Users |
|--------|------|---------------|
| Unified Hub | `/hub/` | All |
| MVS Portal | `/portal/` | Operators |
| Intelligence | `/intel/` | Analysts |
| Marketing | `/marketing/` | Analysts |
| HR | `/hr/` | Architects |
| Pricing | `/pricing/` | Analysts |
| Observability | `/obs/` | Architects |
| Training | `/training/` | All |

### 5.2 API Quick Reference

```bash
# Intelligence overview
GET /fde-api/api/intelligence/overview

# List sources
GET /fde-api/api/intelligence/sources

# Trigger collection
POST /fde-api/api/intelligence/collect
  body: { source_type, url, max_items, metadata }

# RSSHub predefined routes
GET /fde-api/api/intelligence/rsshub/routes

# Supported source types
GET /fde-api/api/intelligence/source-types
```

### 5.3 Environment Variables (Cheat Sheet)

| Variable | Default | Purpose |
|----------|---------|---------|
| `FDE_RSSHUB_BASE_URL` | `http://localhost:1200` | RSSHub instance URL |
| `FDE_CRAWL4AI_BACKEND` | `auto` | crawl4ai backend selection |
| `FDE_CRAWL4AI_TIMEOUT` | `60` | Per-page timeout (seconds) |
| `FDE_EMBEDDING_BACKEND` | `onnx` | Embedding model backend |
| `LITELLM_PROXY_URL` | (env) | LiteLLM proxy endpoint |
| `FDE_MAP_LLM_MODEL` | (empty) | Map interpreter LLM model |
