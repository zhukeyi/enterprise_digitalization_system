# 海关数据底座合规清单（P1-C 三道红线）

> 适用范围：情报模块海关贸易数据底座（C1）+ GEO 定向营销联动（C2）。
> 本清单是上线前必须逐项勾选的合规闸门；任一红线未满足，相关受众不得进入营销触达。

---

## 红线 R1 — 再分发授权（Redistribution Authorization）

**风险**：Tier-2 提单（BOL）平台（Panjiva / ImportGenius / Volza）条款明确禁止原始记录再分发。
若直接对外提供采购商原始行（Shipper/Consignee/Notify/港口/HS），构成违约与潜在侵权。

**控制措施**：

- [ ] 系统只持久化与对外交付 **派生情报**（`BuyerEntity`：品类×港口×进口频次的聚合画像），
      不保留/不导出原始 BOL 行（`BolShipment.raw` 仅作审计，禁止下游读取与转发）。
- [ ] `CustomsScraper._aggregate_buyers` 已确认仅输出聚合画像，原始 consignee 明细不入库查询接口。
- [ ] 免费层（ImportYeti / Zauba）数据以"衍生画像"形态使用，绝不导出原始抓取结果。
- [ ] 付费层（Volza / ImportGenius）上线前，法务确认已签署 **企业级再分发授权**（enterprise redistribution license）；
      未授权前该类源保持 `compliance_flags: [r1_redistribution_license]` 且默认禁用。
- [ ] 对外 API（情报门户 / 营销连接器）返回字段白名单校验：不得包含 `shipper/consignee/notify` 原文。

---

## 红线 R2 — 隐私与反垃圾（Privacy & Anti-Spam）

**风险**：采购商多为企业法人（通常不构成个人信息），但抓取联系人/邮箱即触发
PIPL / GDPR / ePrivacy + CAN-SPAM / CASL 义务；对个人邮箱触达属高风险。

**控制措施**：

- [ ] 触达仅限 **企业级渠道**（企业域名邮箱 / 门户站内信 / 广告定向），个人邮箱（gmail/qq/163…）一律拒绝。
      由 `enterprise_outreach_allowed()` 强制校验，`FREE_EMAIL_DOMAINS` 黑名单生效。
- [ ] 显式 `consent=False` 的受众 **硬拒绝**触达（`OutreachComplianceGate.evaluate`）。
- [ ] 所有邮件类触达必须包含 **一键退订** 链接（`append_unsubscribe_footer()` 自动追加 CAN-SPAM/CASL/GDPR 合规脚注）。
- [ ] 门户/广告类触达不携带任何个人可识别信息（PII）；联系人补全须经合规渠道，禁止爬取个人社媒。
- [ ] 触点频率受控（同受众冷却期），避免构成骚扰；由营销 `push_service` 频控策略保证。

---

## 红线 R3 — 制裁筛查（Sanctions Screening）

**风险**：向 OFAC / EU 制裁名单实体触达，构成严重合规违法。

**控制措施**：

- [ ] 每个 `BuyerEntity` 进入营销分群前必须通过 `SanctionsGuard.screen()`。
- [ ] 生产环境 **必须** 加载官方名单（OFAC SDN / EU Consolidated List）替换内置 SAMPLE：
      `SanctionsGuard.load("path/to/official_denylist.yaml")`。
- [ ] 任何 `hit`（`exact/substring/alias`）即 `blocked=True`，`OutreachComplianceGate` 返回 `allowed=False`。
- [ ] 筛查结果（`SanctionsScreenResult`）留痕审计，可回溯。
- [ ] 命中实体从受众分群中剔除，并标记 `compliance_flags: [r3_sanctions]`。

---

## 上线前总闸（Release Gate）

| 检查项 | 负责人 | 状态 |
| :--- | :--- | :--- |
| R1 派生交付、原始 BOL 不出域 | 数据工程 | ☐ |
| R1 付费源再分发授权已签署 | 法务 | ☐ |
| R2 企业级渠道校验 + 退订脚注 | 营销工程 | ☐ |
| R3 官方制裁名单已加载并拦截生效 | 合规 | ☐ |
| R3 筛查审计留痕可用 | 数据工程 | ☐ |
| 存储增长监控（离线 ETL 保护单机） | 运维 | ☐ |

> 任一 ☐ 未勾选，C2 GEO 联动不得对相应受众开启触达。
