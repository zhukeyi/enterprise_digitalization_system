# FDE ↔ Dify 集成指南

## 概述

将 FDE AI Platform 的数据接入和 RAG 检索能力包装为 Dify 的 Custom Tool，使 Dify 工作流中可以直接调用：

- **文件入库**：上传 Excel/CSV/PDF/DOCX/PPTX → 自动解析 + 向量化 + 全文索引
- **数据问答**：自然语言查询已入库数据 → RAG 检索 + LLM 合成答案
- **任务状态**：查询异步入库进度（适用于大文件批量场景）

## 方式一：导入 OpenAPI 规范（推荐，最简单）

### Step 1：在 Dify 中创建 Custom Tool

1. 打开 Dify → 顶部导航「工具」→「创建自定义工具」
2. 选择「OpenAPI / Swagger」导入方式
3. 上传 `docs/fde-dify-openapi.yaml`
4. Dify 自动解析出 4 个工具：
   - `upload_file` — 文件入库
   - `ask_data` — 数据问答
   - `get_task_status` — 任务状态
   - `health_check` — 健康检查

### Step 2：认证配置

在 Dify 工具配置中添加 API Key 认证：

| 参数 | 值 |
|------|-----|
| 认证类型 | API Key |
| Header 名 | `Authorization` |
| API Key | 你的 FDE API Key（如未开启认证则留空） |

> 当前 FDE 认证中间件未开启 (`FDE_ENABLE_AUTH` 未设置)，可先跳过认证。

### Step 3：在工作流中使用

创建 Dify 工作流，拖入 FDE 工具节点：

```
[开始] → [文件入库: upload_file] → [数据问答: ask_data] → [LLM 总结] → [结束]
```

## 方式二：手动配置 API Tool

如果不方便导入 OpenAPI，可以手动在 Dify 中逐个创建 API 工具：

### Tool 1: 文件入库

| 参数 | 值 |
|------|-----|
| 名称 | 文件入库 |
| 方法 | POST |
| URL | `https://217.142.246.70:8443/fde-api/ingest/upload` |
| 请求体类型 | multipart/form-data |
| 参数 | `file` (binary, 必填), `doc_type` (string, 选填) |

### Tool 2: 数据问答

| 参数 | 值 |
|------|-----|
| 名称 | 数据问答 |
| 方法 | POST |
| URL | `https://217.142.246.70:8443/fde-api/api/data/ask` |
| 请求体类型 | JSON |
| 参数 | `query` (string, 必填), `top_k` (integer, 默认5), `doc_type` (string, 选填) |

## 典型 Dify 工作流示例

### 场景：企业内部数据知识库问答

```
1. [开始节点]
   用户输入："请分析我们上传的销售数据"

2. [FDE 数据问答: ask_data]
   query: 从 LLM 提取的查询关键词
   doc_type: "sales_data"
   → 返回: { answer: "本月销售额最高的区域是杭州...", sources: [...] }

3. [LLM 节点]
   系统提示: "你是数据分析助手。以下是 FDE 检索到的数据：{{FDE_SOURCES}}
   请用中文生成摘要报告。"
   → 返回格式化报告

4. [结束节点]
   输出: 格式化报告 + 数据来源
```

### 场景：批量文档入库 → 自动分类问答

```
1. [开始节点]
   用户上传多个文件

2. [FDE 文件入库: upload_file]  (循环调用)
   对每个文件: 上传 → 自动解析 → 向量化
   doc_type: "供应商合同"

3. [FDE 数据问答: ask_data]
   query: "列出所有2024年到期的合同"
   doc_type: "供应商合同"
   → 返回具体合同信息

4. [LLM 节点]
   将检索结果整理为到期提醒表格

5. [结束节点]
```

## 连接器集成（外部系统数据）

除了文件上传，FDE 的连接器系统还可以从外部数据源拉取数据：

| 数据源 | 状态 | 说明 |
|--------|------|------|
| 数据库 (SQL) | 规划中 | 通过连接器自动同步数据库表 |
| REST API | 规划中 | 定时从 RESTful API 拉取数据 |
| 消息系统 (企微/飞书/钉钉) | 已实现 | IM 消息数据接入 |

## 注意事项

1. **文件大小限制**：同步上传 ≤ 20MB，大文件建议走异步接口
2. **服务器容量**：当前单机 11GB，建议控制单次批量入库的文档量
3. **Dify QPS 限制**：Dify 社区版有 QPS 限制，大批量入库建议直接调 FDE API
4. **认证**：当前 FDE 认证未开启，建议在启用认证前完成 Dify 工具配置