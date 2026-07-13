# 海关数据 → GEO 定向营销联动指南（P1-C）

> 模块归属：情报模块（海关数据底座 C-1~C-7） + 营销模块（GEO 定向联动 C-8~C-12）
> 目标：在 GEO 营销模块中，基于海关数据底座，对进口品类 / 采购商 / 港口维度做**定向内容生成 + 企业级合规推送 + ROI 归因**。

---

## 1. 数据流向与合规边界

```
海关数据底座 (data_agent)
  ├─ TradeRecord (Tier-1 统计, 无买家名)
  └─ BuyerEntity (Tier-2 BOL 衍生画像, 仅聚合, 绝不包含原始提单)
        │  仅传递 BuyerEntity 衍生字段
        ▼
GEO 营销联动层 (marketing_agent)
  C-8 受众连接器  → 分群 (品类 × 港口 × 频次 × 增长) + 制裁筛查
  C-9 定向内容    → 分群定制 GEO 文案 + 多语言 + 关键词机会
  C-10 定向推送    → ReportInstance + 企业渠道 + 退订页脚 (R2)
  C-11 ROI 归因    → 分群作为"渠道", 混合 ROAS + OLS 预测 (≥2 分群)
        ▼
REST API (/api/customs-campaign/*)  ←→ 营销门户 (frontend/marketing-portal)
```

**三条合规红线（不可逾越）**

| 红线 | 含义 | 本模块实现 |
|------|------|-----------|
| R1 再分发授权 | 仅交付 `BuyerEntity` 衍生画像，绝不下发原始 BOL 行 | `customs_models.BuyerEntity` 是唯一跨层载体；推送报告为聚合口径，不列个人 PII |
| R2 隐私与反垃圾 | 仅企业级渠道；邮件需企业域名 + 明示同意 + 退订链接 | `compliance_guard.enterprise_outreach_allowed` + `append_unsubscribe_footer` |
| R3 制裁筛查 | 触达前必须对买家做 OFAC/EU 式筛查 | `compliance_guard.OutreachComplianceGate` 在 C-8 分群与 C-10 推送两处强制校验 |

> ⚠️ 默认制裁名单为 **SAMPLE**（非生产可用）。生产必须调用 `SanctionsGuard.load(path)` 载入官方 OFAC SDN / EU Consolidated 名单。

---

## 2. 后端 API

基址：`/api/customs-campaign`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/segments`   | 构建并列出受众分群（支持 `category`/`port`/`frequency_tier`/`growth_tier`/`min_value_usd`/`min_import_count`/`limit`/`country` 过滤） |
| GET  | `/overview`   | 触达与合规总览（可触达分群数、被拦截买家数、合计进口额） |
| POST | `/content`    | 为指定 `segment_id` 生成 GEO 内容包（brand / brand_id / target_langs） |
| POST | `/push`       | 经企业渠道推送指定分群（`channel`: email/webhook/im/portal） |
| POST | `/roi`        | 跨分群 ROI 归因（`total_budget` 触发 OLS 预测，需 ≥2 个可触达分群） |

### 2.1 分群模型（C-8）

每个分群是 `(品类 HS 章节 × 港口 × 频次档 × 增长档)` 的一个单元：

- `frequency_tier`：`high`(≥20 批次) / `mid`(≥5) / `low` / `unknown`
- `growth_tier`：由 `last_seen` 年份相对当前年推导 `rising`(≤1) / `stable`(≤3) / `declining` / `unknown`
- `compliance_status`：`passed`（无拦截）/ `partial`（部分买家被制裁拦截）/ `blocked`（全部拦截，不可触达）
- `deliverable_buyers`：通过 R3 筛查的买家衍生画像（不含原始 BOL）

### 2.2 内容生成（C-9）

复用 `GEOWriter` / `MultilingualWriter` / `KeywordStrategy`：

- GEO 草稿的事实（facts）注入分群上下文（品类、港口、频次、增长、合计进口额）
- 多语言本地化（en/ja/ko/es/fr + 源语言）
- 关键词机会：从分群 `hs_codes`/`category` 派生商业意图词，若提供 `brand_id` 则融合品牌自有词计划

### 2.3 推送与合规（C-10）

- `portal` / `webhook`：衍生画像即可，无需买家 PII → 一律允许（`enterprise_outreach_allowed(None)` 为 True）
- `email`：需**企业域名**邮箱 + 明示 `consent` + `unsubscribe_url`；通过后在正文强制追加 CAN-SPAM/CASL/GDPR 退订页脚
- 被制裁（`blocked`）或无可触达买家的分群在发送前直接拒绝

### 2.4 ROI 归因（C-11）

将每个可触达分群视为一个广告"渠道"，用透明漏斗模型换算：

```
spend   = cost_per_contact × deliverable_buyers
revenue = deal_value × conversion_rate × deliverable_buyers
roas    = revenue / spend
```

- `PerformanceTracker` 计算混合 ROAS 与渠道排名
- 当可触达分群 ≥2 时，`ROIPredictor`（OLS）以分群为历史数据点，预测给定 `total_budget` 的收入 / ROAS / 利润

---

## 3. 门户使用（营销门户 /marketing/ → Customs Campaign）

1. 进入「海关定向」页，查看分群总览（可触达 / 被拦截 / 合计进口额）。
2. 选择某个分群，点击「生成 GEO 内容」获取定制文案与多语言版本。
3. 选择推送渠道（建议 portal / webhook 企业内网；邮件需企业地址+同意+退订链接）。
4. 查看 ROI 归因面板，评估各分群渠道的 ROAS 与预测回报。

---

## 4. 测试

| 文件 | 覆盖 |
|------|------|
| `agents/marketing_agent/tests/test_customs_audience.py`     | C-8 分群 + 制裁筛查 |
| `agents/marketing_agent/tests/test_customs_campaign_content.py` | C-9 内容生成 |
| `agents/marketing_agent/tests/test_customs_campaign_pusher.py`  | C-10 推送 + 合规 |
| `agents/marketing_agent/tests/test_customs_campaign_roi.py`      | C-11 ROI 归因 |
| `agents/marketing_agent/tests/test_customs_campaign.py`         | C-12 端到端（内存库 + FastAPI） |

运行：

```bash
PYTHONPATH=. python -m pytest agents/marketing_agent/tests/ -q -o addopts=""
```
