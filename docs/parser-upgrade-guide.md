# FDE PDF 解析升级手册（P2-A：Docling 可选后端）

> **阶段**：P2-A RAG 解析升级
> **状态**：已实现，待生产验证
> **更新时间**：2026-07-13

---

## 1. 背景与目标

FDE 平台原有的 PDF 解析依赖 `pdfplumber`，对矢量绘制表格（reportlab 生成）和无显式网格线的表格还原率低（R-2 基线测试中 `extract_tables` 对 reportlab 表格返回 0 行）。

P2-A 引入 [Docling](https://github.com/docling-project/docling) 作为可选 PDF 解析后端，利用其 VLM（Vision Language Model）布局检测能力提升表格和文档结构的还原质量。

**设计原则**：
- Docling 为**可选依赖**，不进入主依赖树（torch ~800MB + VLM 模型 ~1.5GB）
- 通过环境变量 `FDE_PARSER_BACKEND` 控制后端选择
- `auto` 模式下 Docling 优先、未安装自动回退 pdfplumber
- 生产 2C/11G 服务器保持零 torch，仅在升配后启用

## 2. 架构设计

```
parse_file(filename, data)
    └── _parse_pdf(data, filename)
            ├── FDE_PARSER_BACKEND=pdfplumber → _parse_pdf_pdfplumber()
            ├── FDE_PARSER_BACKEND=docling    → _parse_pdf_docling()
            └── FDE_PARSER_BACKEND=auto (默认)
                    ├── try: _parse_pdf_docling()
                    └── except ImportError: _parse_pdf_pdfplumber()
```

### 2.1 Docling 解析流程

```
PDF bytes
    → DocumentStream(name, BytesIO)
    → DocumentConverter().convert(stream)
    → result.document.export_to_markdown()
    → _parse_markdown_to_blocks(md)
    → ParsedDocument(blocks=[HEADING/TABLE/TEXT])
```

### 2.2 Markdown → Block 解析

`_parse_markdown_to_blocks()` 将 Docling 输出的 GitHub 风格 Markdown 转换为结构化 Block：

| Markdown 元素 | Block 类型 | 说明 |
|:---|:---|:---|
| `# 标题` ~ `###### 标题` | `HEADING` | 保留标题文本，丢弃层级（归一化层处理） |
| `| col1 | col2 |` 表格 | `TABLE` | 复用 `_grid_to_table()`，自动去重表头 |
| 其余文本 | `TEXT` | 按行产出 |

**表格解析关键逻辑**：检测 `|---|---|` 分隔行并排除，仅保留表头 + 数据行。

## 3. 环境变量配置

| 变量 | 值 | 行为 |
|:---|:---|:---|
| `FDE_PARSER_BACKEND` | `auto`（默认） | Docling 优先，未安装回退 pdfplumber |
| `FDE_PARSER_BACKEND` | `docling` | 强制 Docling，未安装抛 `ImportError` |
| `FDE_PARSER_BACKEND` | `pdfplumber` | 强制 pdfplumber |

## 4. 安装与启用

### 4.1 独立 venv 安装（推荐）

```bash
# 在服务器上创建独立 venv
python3 -m venv /home/ubuntu/fde-ai-platform/venv-docling
source /home/ubuntu/fde-ai-platform/venv-docling/bin/activate
pip install -r requirements-docling.txt

# 配置后端
echo 'FDE_PARSER_BACKEND=auto' >> .env

# 重启后端
sudo systemctl restart fde-backend
```

### 4.2 首次运行注意事项

Docling 首次解析 PDF 时需从 HuggingFace 下载 VLM 模型：

- **模型列表**：layout detection + table detection + OCR
- **总大小**：约 1.5GB
- **存储位置**：`~/.cache/huggingface/hub/`
- **网络要求**：需访问 `huggingface.co`（中国大陆可能需配置镜像）

若网络不可达，`auto` 模式会自动回退到 pdfplumber，不影响服务可用性。

## 5. R-2 回归对比结果

### 5.1 测试样本

使用 reportlab 生成含 4 列 × 6 行表格的 PDF（供应商采购明细表）。

### 5.2 pdfplumber 基线

| 指标 | 结果 |
|:---|:---|
| 表格数 | 1 |
| 数据行数 | 5/5 (100%) |
| 标题块 | 0 |
| 文本含关键词 | 否 |

> **注**：reportlab 生成的表格有显式 `GRID` 边框，pdfplumber 能提取。对于矢量绘制无网格线的表格，`extract_tables` 常返回 0 行——这正是 Docling VLM 要解决的痛点。

### 5.3 Docling 后端

Docling VLM 模型需从 HuggingFace 下载，当前开发环境网络不可达（502 Bad Gateway），代码路径已验证（导入 + API 调用正确），在有 HF 访问的生产环境可跑通。

**预期优势**（基于 Docling 官方基准）：
- 矢量绘制/扫描件表格：Docling VLM 可识别无网格线表格布局
- 标题/正文结构化：Docling 输出 Markdown 保留标题层级
- 复杂多栏布局：Docling 布局模型可正确识别阅读顺序

## 6. 测试覆盖

| 测试文件 | 测试数 | 说明 |
|:---|:---|:---|
| `tests/test_parsers_docling.py` | 10 | 8 pass + 2 skip（无 docling 环境） |

测试覆盖：
- Markdown → Block 纯函数（标题/文本/表格/分隔行排除）
- 后端选择逻辑（auto/pdfplumber/docling）
- auto 模式回退路径（monkeypatch 验证）
- 显式 docling 未装抛 ImportError
- 真实 Docling 解析（skip if 未装）

## 7. 运维命令

```bash
# 查看当前生效的后端
curl -s https://localhost:8443/fde-api/api/health | jq .parser_backend

# 运行 R-2 回归对比脚本
/path/to/venv-docling/bin/python scripts/r2_docling_regression.py

# 切换后端（无需重启，下次请求生效）
# 注意：_PDF_BACKEND 在模块加载时读取，需重启服务才能切换
sudo systemctl restart fde-backend
```

## 8. 故障排查

| 症状 | 原因 | 解决 |
|:---|:---|:---|
| 服务启动失败 | docling 显式模式但未安装 | 改 `FDE_PARSER_BACKEND=auto` 或安装依赖 |
| 解析超时 | VLM 模型首次下载 | 预下载模型或设超时回退 |
| 内存告警 | torch + VLM 占用 >2GB | 升配或回退 pdfplumber |
| 表格还原率未提升 | 简单表格 pdfplumber 已够用 | Docling 优势在复杂/扫描件 |

## 9. 后续计划

- **R-2 生产验证**：在服务器有 HF 访问时运行回归脚本，产出真实对比数据
- **P2-B Vanna NL2SQL**：分析层升级，复用 Qdrant 向量库
- **P3 Langfuse**：观测持久化（需升配）
