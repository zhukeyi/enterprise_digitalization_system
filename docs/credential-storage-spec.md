# 凭证存储规范（Credential Storage Spec）

> 落实工程评审 **F13**：连接器 / IM 的 AppID / Secret / Token 不明文存储。
> 配合 `master-delivery-plan.md` §2.2 与 `connector-contract.md`。

---

## 1. 禁止事项

- ❌ 任何密钥明文写入代码、配置、`*.yaml`（除非被 secret manager 注入）。
- ❌ 任何密钥明文落 `connector_registry` 或日志 / 审计字段。
- ❌ 密钥进 Git 历史（CI 加 `gitleaks` / `detect-secrets` 扫描）。

---

## 2. 推荐方案（按优先级）

1. **外部 Secret Manager（首选）**：AWS Secrets Manager / Vault / K8s Secret。
   `connector_registry` 仅存 secret 引用（ARN / path），运行时解析。
2. **数据库 pgcrypto 加密列（本机兜底）**：无外部 SM 时，密钥用 `pgcrypto`
   对称加密（`pgp_sym_encrypt`）存入 `connector_registry.credentials_encrypted`。
   密钥 `FDE_PGP_KEY` 由 **环境变量 / SM** 提供，绝不入库。

---

## 3. pgcrypto 加密列实现约定

字段：`connector_registry.credentials_encrypted`（`TEXT`，仅密文）。

- **写入**（DAO 层负责，不在 ORM 模型值内明文）：
  ```sql
  INSERT INTO connector_registry (..., credentials_encrypted)
  VALUES (..., pgp_sym_encrypt(:secret_json, current_setting('app.pgp_key')));
  ```
  密钥通过 `SET app.pgp_key = :key`（会话级，来自 `FDE_PGP_KEY`）注入，不拼接到 SQL。
- **读取**：仅在需要调用连接器时由服务端解密到内存，**不**回写、不记录。
- **轮换**：`FDE_PGP_KEY` 变更后，由运维脚本对存量行重新加密（停机窗口或双密钥过渡）。
- **IM 凭证**：`im_agent` 的 AppID/Secret 同理存于独立表或复用本列约定。

---

## 4. 代码层辅助

提供 `shared/utils/crypto.py`：

- `build_encrypt_expr(plaintext_literal, key_setting="app.pgp_key")` →
  返回 `sqlalchemy.text("pgp_sym_encrypt(:v, current_setting('app.pgp_key'))")`
  与绑定参数，供 DAO 安全构建写入语句（无 DB 也可 import，便于单测）。
- `build_decrypt_expr(column)` → 对应解密表达式。

> 注意：加密/解密发生在数据库层（pgcrypto），代码只负责构造**参数化**语句，
> 绝不拼接密钥或明文到 SQL 字符串。

---

## 5. 校验清单（Stage Gate）

- [ ] `grep -Rni "secret\|password\|token" config/*.yaml` 无明文值。
- [ ] `connector_registry.credentials_encrypted` 写入走参数化加密。
- [ ] `FDE_PGP_KEY` 来自环境变量 / SM，CI 用占位符。
- [ ] 单测验证构造的 SQL 不含明文密钥（字符串断言）。
