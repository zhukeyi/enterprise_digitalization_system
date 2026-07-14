# FDE AI Platform - Certification Process

> Three-tier certification system for the FDE AI Platform. Covers exam standards, scoring, issuance, and renewal.
> Companion to `manual.md`, `exam-bank.md`, and `video-scripts.md`.

---

## 1. Certification Tiers

| Tier | Title | Role | Exam Duration | Passing Score | Validity |
|------|-------|------|---------------|---------------|----------|
| L1 | Operator | Daily operations under guidance | 60 min | 70% | 2 years |
| L2 | Analyst | Independent module configuration and analysis | 90 min | 75% | 2 years |
| L3 | Architect | Solution design, Dify orchestration, compliance | 120 min | 80% | 2 years |

### Prerequisites

| Tier | Prerequisite |
|------|-------------|
| L1 | None (open entry) |
| L2 | L1 certification held |
| L3 | L2 certification held + 6 months platform experience |

---

## 2. Exam Structure

### 2.1 Level 1: Operator (60 min, 20 questions, 100 points)

| Section | Type | Count | Points Each | Total |
|---------|------|-------|-------------|-------|
| Knowledge | Single choice | 8 | 3 | 24 |
| Compliance | True/False | 6 | 3 | 18 |
| Hands-on | Practical | 4 | 8 | 32 |
| Judgment | Scenario | 2 | 13 | 26 |
| **Total** | | **20** | | **100** |

### 2.2 Level 2: Analyst (90 min, 15 questions, 100 points)

| Section | Type | Count | Points Each | Total |
|---------|------|-------|-------------|-------|
| Knowledge | Single choice | 7 | 5 | 35 |
| Comprehension | Multiple choice | 3 | 7 | 21 |
| Hands-on | Practical | 3 | 12 | 36 |
| Analysis | Scenario | 2 | 4 | 8 |
| **Total** | | **15** | | **100** |

### 2.3 Level 3: Architect (120 min, 15 questions, 100 points)

| Section | Type | Count | Points Each | Total |
|---------|------|-------|-------------|-------|
| Knowledge | Single choice | 5 | 4 | 20 |
| Application | Scenario | 4 | 8 | 32 |
| Design | System Design | 3 | 12 | 36 |
| Architecture | Architecture | 3 | 4 | 12 |
| **Total** | | **15** | | **100** |

---

## 3. Exam Administration

### 3.1 Delivery Methods

| Method | Description | Use Case |
|--------|------------|----------|
| Online (platform) | `/training/` portal, auto-graded for objective questions | Standard |
| Proctored online | Screen share + camera monitoring | Certified exam |
| In-person | Paper or laptop at training center | High-stakes certification |

### 3.2 Practical Exam Evaluation

Practical questions are evaluated by:

1. **Automated checks**: Screenshot uploaded; system verifies expected outcome (file ingested, collection succeeded).
2. **Human review**: Certified examiner reviews screenshots and written answers using a scoring rubric (see exam bank answers).

### 3.3 Retake Policy

| Scenario | Policy |
|----------|--------|
| First failure | Retake after 7 days |
| Second failure | Retake after 30 days + mandatory retraining |
| Third failure | Retake after 90 days + full course retake |
| Maximum retakes | 5 per year |

---

## 4. Certificate Issuance

### 4.1 Certificate Template

```
+==============================================================+
|                    FDE AI PLATFORM                           |
|              CERTIFICATION OF COMPLETION                     |
|                                                              |
|  This certifies that                                        |
|                                                              |
|                    [Name]                                   |
|                                                              |
|  has successfully completed the                              |
|  [Level X] [Operator/Analyst/Architect] Certification       |
|                                                              |
|  Exam Date: [Date]      Score: [XX]%                        |
|  Certificate ID: [UUID]  Valid Until: [Date+2yr]           |
|                                                              |
|  Issued by: FDE AI Platform Training Authority              |
+==============================================================+
```

### 4.2 Certificate ID Format

```
FDE-[LEVEL]-[YYYY]-[SEQUENCE]
```

Examples:
- `FDE-L1-2026-0001` -- First L1 certificate in 2026
- `FDE-L3-2026-0012` -- Twelfth L3 certificate in 2026

### 4.3 Verification

- Certificates can be verified at `/training/verify?id=FDE-L1-2026-0001`
- Each certificate has a unique UUID stored in the platform database
- Verification returns: name, level, issue date, expiry date, score

---

## 5. Renewal and Continuing Education

### 5.1 Renewal Requirements

| Tier | Renewal Requirement |
|------|-------------------|
| L1 | Retake L1 exam OR complete 8 hours of continuing education |
| L2 | Retake L2 exam OR complete 16 hours of continuing education + 1 project report |
| L3 | Retake L3 exam OR complete 24 hours of continuing education + 1 architecture case study |

### 5.2 Continuing Education Credits

| Activity | Credits |
|----------|---------|
| Attend FDE training webinar (1h) | 1 |
| Complete new module training video | 2 |
| Submit successful use case | 5 |
| Present at FDE user conference | 10 |
| Contribute to FDE open source | 5 |

1 credit = 1 hour of continuing education.

### 5.3 Expiry and Lapse

| Status | Action |
|--------|--------|
| Expires in 90 days | System sends reminder email |
| Expired | Must retake full exam (no continuing education option) |
| Expired over 1 year | Must retake all prerequisite tiers |

---

## 6. PPT Training Deck Outline

> 40-slide training deck. Each slide corresponds to a section in the manual.
> Recommended tool: PowerPoint, Google Slides, or Marp (Markdown to PPTX).

### Section 1: Introduction (5 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 1 | Title slide | FDE AI Platform logo, course title, instructor name, date |
| 2 | Agenda | 7-step method overview, certification tiers, course schedule |
| 3 | Platform positioning | "AI Landing Operating System" concept, B2B value proposition |
| 4 | Seven-Step Method | Table of 7 steps with one-line value and portal path |
| 5 | System architecture | Deployment topology diagram (Nginx -> FastAPI -> LiteLLM/Qdrant/RSSHub/Dify) |

### Section 2: Foundation - Knowledge Ingestion (5 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 6 | Step 1 overview | Pipeline: Upload -> Parse -> Normalize -> Chunk -> Embed -> Store |
| 7 | Supported formats | xlsx, csv, pdf, docx, pptx icons |
| 8 | Upload demo | Screenshot of `/portal/` upload page |
| 9 | Q&A demo | Screenshot of natural language query with source citations |
| 10 | Red lines | R1: No PII uploads, R5: No disabling audit logging |

### Section 3: Delivery - Dashboard (3 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 11 | Step 2 overview | Dashboard turns data into executive-readable views |
| 12 | KPI cards and anomaly detection | Screenshot of dashboard with red-highlighted metric |
| 13 | Drill-down and export | Screenshot of drill-down view and PDF export |

### Section 4: Intelligence (5 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 14 | Step 4 overview | External intelligence amplifier |
| 15 | Source types | 6 source types: web, rss, api, customs, rsshub, crawl4ai |
| 16 | RSSHub routes | Predefined route categories screenshot |
| 17 | Alerts and trends | Keyword alert setup, 14-day trend chart |
| 18 | Customs trade data | Tier-1/Tier-2, compliance red lines (R1-R3) |

### Section 5: Marketing - GEO (4 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 19 | Step 5 overview | GEO: get AI search engines to recommend you |
| 20 | GEO index and E-E-A-T | Definition of GEO index, E-E-A-T framework |
| 21 | Content Studio demo | Article generation screenshot |
| 22 | ROI and A/B testing | ROAS definition, significance testing (p < 0.05) |

### Section 6: Pricing (4 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 23 | Step 7 overview | Dynamic pricing engine |
| 24 | Price elasticity | Coefficient explanation, -1.5 example |
| 25 | What-if simulator | Screenshot of +5% scenario |
| 26 | Red line R3 | Pricing suggestions are advisory; human approval required |

### Section 7: Downsizing (4 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 27 | Step 6 overview | Intelligent redundancy assessment |
| 28 | Foolproof 5 steps | Flowchart of 5 mandatory steps |
| 29 | Risk levels | Low/Medium/High explanation |
| 30 | Red line R2 | Cannot bypass foolproof dialog |

### Section 8: Dify and Advanced (4 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 31 | Dify integration | Custom tool import, workflow orchestration |
| 32 | Preset workflows | Contract analysis, data Q&A, intelligence briefing |
| 33 | Compliance and audit | RBAC/ABAC, audit trail, sanctions screening |
| 34 | Observability | `/obs/` platform: health, token router, RAG inspector, audit trail |

### Section 9: Certification (4 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 35 | Certification tiers | L1/L2/L3 table with duration, passing score, validity |
| 36 | Exam structure | Question types and point distribution per tier |
| 37 | Certification process | Exam -> grading -> certificate issuance -> renewal |
| 38 | Certificate sample | Template display |

### Section 10: Closing (2 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 39 | Summary | Key takeaways, red lines recap, next steps |
| 40 | Q&A | Contact info, resource links, feedback QR code |

---

## 7. PPT Design Guidelines

### 7.1 Visual Style

| Element | Specification |
|---------|--------------|
| Color scheme | FDE brand colors (primary: #00D4FF cyan, secondary: #A855F7 purple) |
| Font | Headings: Inter Bold; Body: Inter Regular; Code: SF Mono |
| Slide size | 16:9 (1920x1080) |
| Logo placement | Top-left corner, 120px wide |
| Footer | Slide number bottom-right, "FDE AI Platform" bottom-left |

### 7.2 Content Rules

- Maximum 6 bullet points per slide
- Maximum 30 words per slide (excluding diagrams)
- Every concept slide must have a diagram or screenshot
- Every demo slide must have a full-resolution screenshot
- Red line slides must use red accent color for emphasis

### 7.3 Animation

- Use "fade" transitions only (no bounce, spin, or fly-in)
- Animate bullet points sequentially on complex slides
- No animation on red line or compliance slides (solemn tone)

---

## 8. Exam Day Checklist

### For Candidates

- [ ] Arrive 15 minutes before exam start
- [ ] Bring photo ID for in-person exams
- [ ] Ensure laptop is charged (for proctored online)
- [ ] Close all non-exam applications
- [ ] Have platform credentials ready
- [ ] Prepare screenshot tool (for practical questions)

### For Examiners

- [ ] Verify candidate identity
- [ ] Confirm platform is accessible and healthy
- [ ] Distribute exam credentials (if separate from training)
- [ ] Set exam timer (60/90/120 min per tier)
- [ ] Prepare grading rubric for practical questions
- [ ] Have retake policy documentation available
