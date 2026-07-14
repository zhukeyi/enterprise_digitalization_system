# FDE AI Platform - Certification Exam Bank

> Companion to `manual.md`. Three-tier certification: Level 1 (Operator) / Level 2 (Analyst) / Level 3 (Architect).
> Question types: Single choice, Multiple choice, True/False, Practical, Scenario, System Design.
> Total: 50 questions. Answers at the end.

---

## Level 1: Operator Certification (20 questions)

### Single Choice

1. Which file format is NOT supported for knowledge ingestion?
   A. xlsx  B. pdf  C. mp4  D. docx

2. What is the path of the unified navigation page?
   A. `/portal/`  B. `/hub/`  C. `/intel/`  D. `/`

3. When an intelligence alert keyword is matched, what does the system do?
   A. Auto-sends email  B. Generates a trigger record  C. Deletes the database  D. No action

4. Which module provides the knowledge ingestion + unified retrieval base?
   A. Step 4 (Intelligence)  B. Step 1 (Foundation)  C. Step 7 (Pricing)  D. Step 6 (Downsizing)

5. What is the RSSHub default port on the FDE platform?
   A. 4000  B. 6333  C. 1200  D. 8000

6. Which page should an operator visit to upload a file for knowledge ingestion?
   A. `/intel/`  B. `/portal/` -> Upload  C. `/pricing/`  D. `/obs/`

7. What does the "Trends" page in the intelligence portal show?
   A. Employee headcount trends  B. 14-day collection curve and keyword cloud  C. Stock price trends  D. Server uptime

8. What is the memory safety line for the host machine?
   A. 50%  B. 60%  C. 70%  D. 90%

### True/False

9. ( ) You can upload a spreadsheet containing employee ID numbers directly to the knowledge base for Q&A.

10. ( ) Pricing suggestions from the system can be directly executed as final selling prices without human approval.

11. ( ) You should log out of the platform when leaving your workstation.

12. ( ) The foolproof dialog in the downsizing simulator can be skipped if the manager approves verbally.

13. ( ) RSSHub routes can be subscribed to through the intelligence portal's Sources page.

14. ( ) Audit logging can be disabled to improve system performance.

### Practical

15. Upload a monthly sales report (PDF) to `/portal/`, then ask in natural language: "Which region had the highest sales this month?" Screenshot the answer.

16. On `/intel/` -> Sources page, trigger a collection from the RSSHub route `/reuters/business` with max_items=20. Screenshot the result count.

17. On `/obs/` health dashboard, identify any components showing a warning or error state. Document the component name and status.

18. On `/portal/dashboard`, identify which metrics are highlighted in red (anomalies). List the metric names and their current values.

### Scenario

19. Your manager asks you to quickly find all intelligence items mentioning "semiconductor export controls" from the past 7 days. Describe the exact steps you would take on the platform.

20. A colleague tells you they accidentally uploaded a file containing customer bank account numbers. What should you do immediately?

---

## Level 2: Analyst Certification (15 questions)

### Single Choice

21. What does the GEO index measure?
   A. Website traffic  B. Brand citation rate by AI search engines  C. Ad click-through rate  D. Employee satisfaction

22. A price elasticity coefficient of -1.5 means:
   A. Raise price 1% -> demand drops 1.5%  B. Raise price 1% -> demand rises 1.5%  C. No correlation  D. Zero elasticity

23. What regression method is used for ROI prediction in the customs campaign module?
   A. Decision tree  B. Neural network  C. OLS (Ordinary Least Squares)  D. Random forest

24. In E-E-A-T content optimization, what does the second "E" stand for?
   A. Efficiency  B. Expertise  C. Engagement  D. Economy

25. ROAS stands for:
   A. Return on Ad Spend  B. Revenue on Annual Sales  C. Rate of Active Sessions  D. Regional Optimization Analysis System

26. Which data source type produces LLM-ready Markdown output from web pages?
   A. `web`  B. `rss`  C. `crawl4ai`  D. `api`

27. What is the customs data compliance rule R1?
   A. Only derived BuyerEntity data is exposed (zero raw BOL)  B. All data must be free  C. Data must be less than 30 days old  D. Data must be in English

### Multiple Choice

28. Which views does the dynamic pricing module include? (Select all that apply)
   A. Overview  B. What-if Simulator  C. Strategy Optimizer  D. Elasticity Analysis  E. Competitor Monitor

29. Which views does the intelligence center include? (Select all that apply)
   A. Sources  B. Trends  C. Reports  D. Alerts  E. Dashboard

30. Which of the following are RSSHub predefined route categories on the FDE platform? (Select all that apply)
   A. news_global  B. tech_industry  C. trade_policy  D. china_trade  E. financial_markets

### Practical

31. On `/pricing/` -> Elasticity Analysis, read the elasticity coefficient for a product. Then in the Simulator, calculate the profit change for a 5% price increase. Write the formula, substituted values, and conclusion.

32. On `/marketing/` -> Content Studio, generate an E-E-A-T optimized article about "sustainable packaging in export trade". Then create an A/B variant. Screenshot both versions and document the differences.

33. On `/intel/` -> Customs view, search for trade records with HS code 8517 (telecom equipment). Export the trend analysis and document the top 3 importer countries.

### Scenario

34. The marketing team reports that GEO index has dropped 15% over the past month. As an analyst, outline your investigation steps using the platform's tools, and describe what data you would examine to diagnose the cause.

35. A product's price elasticity changed from -0.8 to -2.3 over two quarters. What does this mean for pricing strategy? Describe how you would use the platform to investigate and what recommendation you would make.

---

## Level 3: Architect Certification (15 questions)

### Single Choice

36. What is the Dify provider name used to import FDE tools?
   A. fde_tool  B. fde_data_tool  C. fde_api  D. workbuddy

37. How many steps are in the downsizing simulator's foolproof process?
   A. 3 steps  B. 4 steps  C. 5 steps  D. 6 steps

38. Which environment variable controls the crawl4ai backend selection?
   A. `FDE_CRAWL4AI_MODE`  B. `FDE_CRAWL4AI_BACKEND`  C. `CRAWL4AI_CONFIG`  D. `FDE_SCRAPER_TYPE`

39. What is the LiteLLM memory limit on the 11G host?
   A. 512 MB  B. 1 GB  C. 1.5 GB  D. 2 GB

40. Which Python package is NOT allowed in numpy math modules?
   A. numpy  B. scipy  C. pandas  D. math

### Scenario

41. A department shows 40% redundancy rate, 8M CNY annual savings, and "High" risk level. As an architect, what key information would you record in the foolproof step 5 snapshot? How would you explain the "High" risk trade-off to the CEO?

42. A client wants to set the navigation page as the domain root (`/`), but the root path is currently occupied by Dify. Provide a migration plan with at least 3 key steps.

43. The host memory usage has reached 72% after deploying RSSHub and crawl4ai. What actions should you take? Describe the decision tree.

44. A client needs to integrate FDE with their existing CRM system via Dify. Outline the integration architecture, including which FDE tools to expose, how to configure the Dify workflow, and what compliance checks are needed.

### System Design

45. Design a Seven-Step Method landing sequence for a manufacturing client. Explain the dependency relationship between Step 2 (Delivery) and Step 4 (Intelligence).

46. Design a multi-tenant deployment for a SaaS provider serving 5 enterprise clients. Cover: tenant isolation strategy, LiteLLM virtual key management, resource quotas, and monitoring approach.

47. A client's RAG retrieval quality has degraded (MRR dropped from 0.72 to 0.58). Design a debugging plan using the `/obs/` RAG Inspector, including: what metrics to check, how to identify problematic chunks, and what remediation steps to take.

### Architecture

48. Draw the FDE platform's deployment topology on a single Oracle ARM host. Label all services, ports, and data flows. Explain why host networking is used for LiteLLM.

49. The client wants to add a new data source type: "ERP Connector" that pulls data from SAP via OData. Design the implementation plan: new SourceType enum, scraper class, registry registration, API endpoint, and portal view changes.

50. Design a disaster recovery plan for the FDE platform covering: (a) database failure (Postgres for LiteLLM, SQLite for FDE MVS), (b) Qdrant vector database corruption, (c) LiteLLM proxy unavailability, and (d) host machine failure. Include RTO/RPO targets.

---

## Answers

### Level 1 (Operator)

| # | Answer | Explanation |
|---|--------|-------------|
| 1 | C | mp4 is not a supported ingestion format; supported: xlsx, csv, pdf, docx, pptx |
| 2 | B | `/hub/` is the unified Seven-Step navigation page |
| 3 | B | Keyword match generates a trigger record in the alerts system |
| 4 | B | Step 1 (Foundation) provides knowledge ingestion + unified retrieval |
| 5 | C | RSSHub runs on port 1200 (LiteLLM=4000, Qdrant=6333, FDE=8000) |
| 6 | B | `/portal/` -> Upload page for file ingestion |
| 7 | B | Trends page shows 14-day collection curve and keyword cloud |
| 8 | C | Host memory safety line is 70% (~7.7 GB on 11G host) |
| 9 | False | PII (ID numbers) must not be uploaded; ingestion screens for sensitive data |
| 10 | False | Pricing suggestions are advisory; final prices require human approval (Red Line R3) |
| 11 | True | Always log out when leaving workstation (security best practice) |
| 12 | False | Foolproof dialog cannot be skipped; it is system-enforced |
| 13 | True | RSSHub routes can be subscribed via Sources page or API |
| 14 | False | Audit logging must not be disabled; all key operations must be traceable (Red Line R5) |
| 15 | Practical: Verify against actual platform output |
| 16 | Practical: Verify against actual platform output |
| 17 | Practical: Verify against actual platform output |
| 18 | Practical: Verify against actual platform output |
| 19 | Steps: 1. Go to `/intel/` -> Items page; 2. Use search/filter for "semiconductor export controls"; 3. Set date range to last 7 days; 4. Export results |
| 20 | Steps: 1. Immediately contact the system administrator; 2. The admin should remove the document from the vector store; 3. Audit who accessed it; 4. Document the incident; 5. Re-train staff on Red Line R1 |

### Level 2 (Analyst)

| # | Answer | Explanation |
|---|--------|-------------|
| 21 | B | GEO index = brand citation rate by AI search engines |
| 22 | A | Elasticity -1.5: 1% price increase -> 1.5% demand decrease |
| 23 | C | ROI prediction uses OLS regression (numpy-only, no sklearn) |
| 24 | B | E-E-A-T = Experience, Expertise, Authoritativeness, Trustworthiness |
| 25 | A | ROAS = Return on Ad Spend |
| 26 | C | `crawl4ai` source type produces LLM-ready Markdown |
| 27 | A | R1: Only derived BuyerEntity exposed, zero raw BOL data |
| 28 | A B C D E | All 5 views: Overview, What-if, Strategy, Elasticity, Competitor |
| 29 | A B C D | Sources, Trends, Reports, Alerts (Dashboard is a separate portal) |
| 30 | A B C D | news_global, tech_industry, trade_policy, china_trade (no financial_markets) |
| 31 | Formula: profit = (price * 1.05 - cost) * demand * (1 + 0.05 * elasticity). Substitute actual values from platform and conclude whether profit increases or decreases. |
| 32 | Practical: Verify generated content and A/B variant differences |
| 33 | Practical: Verify HS code 8517 search results and top importers |
| 34 | Investigation steps: 1. Check `/marketing/` GEO Dashboard for trend; 2. Review Content Studio output quality; 3. Check Ad Management CTR changes; 4. Examine competitor activity in Intelligence portal; 5. Correlate with external events via RSSHub feeds; 6. Formulate hypothesis and recommend content/strategy adjustment. |
| 35 | Elasticity change from -0.8 (inelastic) to -2.3 (elastic) means demand is now much more price-sensitive. Investigation: check competitor pricing (Competitor Monitor), market conditions (Intelligence), and seasonality. Recommendation: avoid price increases; consider promotional pricing or value-add strategies. |

### Level 3 (Architect)

| # | Answer | Explanation |
|---|--------|-------------|
| 36 | B | Provider name is `fde_data_tool` |
| 37 | C | 5 steps: Reversibility -> Impact -> Explanation -> Confirmation -> Archive |
| 38 | B | `FDE_CRAWL4AI_BACKEND` controls backend (auto/crawl4ai/fallback) |
| 39 | C | 1.5 GB (512 MB causes OOM exit 137) |
| 40 | C | pandas is NOT installed in the venv; numpy-only modules required |
| 41 | Snapshot records: department, affected headcount, savings amount, irreversible impacts, alternative plans, approval chain. CEO explanation: "High" risk means PR/legal costs may exceed the 8M savings; recommend phased approach with retraining option. |
| 42 | Migration plan: 1. Change Dify env vars `APP_WEB_URL`/`CONSOLE_WEB_URL` to add `/dify/` prefix; 2. Update nginx: redirect `/` to hub, add `/dify/` reverse proxy to Dify container; 3. Full regression test all portals and API endpoints. |
| 43 | Decision tree: 1. Check if RSSHub Redis cache is evicting too aggressively (increase maxmemory); 2. Check if crawl4ai is running concurrent pages (limit to 1); 3. If still > 70%, deploy crawl4ai worker on separate machine per resource-assessment-p1a.md; 4. Monitor with `/obs/` health dashboard. |
| 44 | Integration: 1. Expose FDE tools via OpenAPI spec (`docs/fde-dify-openapi.yaml`); 2. In Dify, import as Custom Tool with provider `fde_data_tool`; 3. Build Dify workflow: CRM trigger -> FDE data query -> LLM enrichment -> CRM update; 4. Compliance: ensure no PII flows to LLM, audit log all tool calls, set rate limits. |
| 45 | Sequence: 1 -> 2 -> 3 -> 4 -> 6 -> 5 -> 7. Step 2 depends on Step 1's data base; Step 4 can parallel with Step 2 but reports need Step 2's dashboard for presentation. Step 6 (downsizing) should come before Step 5 (marketing) to optimize headcount first. |
| 46 | Multi-tenant: 1. LiteLLM virtual keys per tenant (stored in Postgres); 2. Qdrant collection-per-tenant or payload-level tenant_id filtering; 3. Resource quotas via LiteLLM rate limits; 4. Per-tenant observability dashboard in `/obs/`; 5. Nginx path-based routing or subdomain-based routing. |
| 47 | Debugging plan: 1. Open `/obs/` -> RAG Inspector; 2. Check MRR trend, recall@k, and per-query scores; 3. Filter for queries with MRR < 0.5; 4. Inspect retrieved chunks for relevance; 5. Check if chunk boundaries changed (ingestion pipeline audit); 6. Verify embedding model (ONNX BGE) consistency; 7. Remediate: re-chunk affected documents, adjust BM25/RRF weights, or re-ingest with Docling parser. |
| 48 | Topology: Nginx(443) -> FastAPI(8000) -> LiteLLM(4000, host networking for Postgres access), Qdrant(6333), RSSHub(1200), Dify. Host networking for LiteLLM because it needs to reach host Postgres on 127.0.0.1:5432 for virtual key storage. |
| 49 | Implementation: 1. Add `ERP = "erp"` to SourceType enum; 2. Create `agents/data_agent/scrapers/erp_scraper.py` extending BaseScraper; 3. Register in ScraperRegistry.create_default(); 4. Add API endpoint in router.py; 5. Add ERP source type card in SourceView.vue; 6. Write integration tests; 7. Document in source-expansion-guide.md. |
| 50 | DR plan: (a) Postgres failure -> LiteLLM keys cached in memory, restart Postgres from backup; RTO 15min, RPO 1h. (b) Qdrant corruption -> Re-embed from source documents (stored in ingestion store); RTO 2h, RPO 0 (source docs retained). (c) LiteLLM unavailable -> Fallback to direct provider API (Mock adapter); RTO 5min, RPO 0. (d) Host failure -> Restore from git + Docker volumes; RTO 4h, RPO 24h. |
