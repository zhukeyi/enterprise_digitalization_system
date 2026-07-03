# FDE AI Platform v1.0.0 — Security Audit Report

**Date**: 2026-07-03
**Tool**: pip-audit 2.10.1 (PyPI Advisory Database)
**Scope**: All Python dependencies in pyproject.toml (core + optional extras)

---

## Summary

| Metric                  | Value |
|-------------------------|-------|
| Total packages scanned  | ~120  |
| Known vulnerabilities   | 0     |
| Status                  | PASS  |

---

## Scan Results

### Initial Scan

- **pip 25.3**: 4 vulnerabilities (PYSEC-2026-196, CVE-2026-1703, CVE-2026-3219, CVE-2026-6357)
  - **Action**: Upgraded pip to 26.1.2
  - **Re-scan**: All 4 vulnerabilities resolved

### Post-Fix Scan

```
No known vulnerabilities found
```

---

## Dependencies Scanned

### Core
- fastapi, uvicorn, pydantic, pydantic-settings, httpx, python-multipart, pyyaml, orjson, langgraph, langchain-core

### Router
- openai

### RAG
- qdrant-client, sentence-transformers, torch, langchain, langchain-community, pymupdf, python-docx, openpyxl, python-pptx, markdown-it-py, rank-bm25, jieba, tiktoken

### Governance
- SQLAlchemy, asyncpg, alembic, redis, python-jose, passlib, python-ldap, pydantic[email]

### Data
- scrapy, beautifulsoup4, lxml, feedparser, newspaper3k, clickhouse-connect, jinja2, matplotlib, apscheduler

### Analysis
- pandas, numpy, plotly

### Observability
- opentelemetry-api, opentelemetry-sdk, opentelemetry-instrumentation-fastapi, opentelemetry-exporter-otlp, prometheus-client, langfuse

### Dev
- pytest, pytest-asyncio, pytest-cov, pytest-mock, black, ruff, mypy, pre-commit

### Eval
- ragas, datasets

---

## Static Security Considerations

1. **SQL Injection**: NL2SQL engine has multi-layer defense (statement whitelist + keyword blacklist + parameterized execution)
2. **XSS**: Frontend uses Vue3 template escaping; CSP headers configured in nginx
3. **Authentication**: JWT + API Key with RBAC/ABAC enforcement; bcrypt>=4.0 for password hashing
4. **Secrets**: Environment variable based configuration; no hardcoded secrets in codebase
5. **Dependency Pinning**: Qdrant client pinned to <1.14; bcrypt pinned to <5.0 (passlib compatibility)
6. **HTTPS**: nginx configured with HSTS, TLS 1.2/1.3 only, certbot auto-renewal

---

## Recommendations

1. **Regular scanning**: Run `pip-audit` weekly in CI/CD pipeline
2. **Dependabot**: Enable GitHub Dependabot for automated vulnerability alerts
3. **SBOM**: Generate CycloneDX SBOM for compliance: `pip-audit --format cyclonedx-json`
4. **License audit**: Run `pip-licenses` to verify all dependencies are compatible with MIT license

---

## Conclusion

FDE AI Platform v1.0.0 has **zero known vulnerabilities** in its Python dependency tree after remediating the pip self-vulnerability. The static security posture includes defense-in-depth across SQL injection, XSS, authentication, and transport security.
