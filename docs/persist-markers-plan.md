# MapAI 点位持久化 + 备注标签化 + 资源面板 方案

> 2026-07-04 | 4 个子模块 | 预计 6-8 小时

---

## 一、需求概述

| # | 需求 | 说明 |
|---|------|------|
| 1 | 点位持久化 | 在地图上标记的点位保存到服务端，刷新不丢失 |
| 2 | 标记时输入备注 | 标点弹出输入框同时输入备注文字 |
| 3 | 备注自动标签化 | 后端将备注文本转为结构化标签（关键词提取） |
| 4 | 左侧资源面板 | 悬浮窗展示所有已治理点位，支持搜索（名称/标签） |

---

## 二、架构设计

```
┌─────────────────────────────────────────────────────┐
│                     前端 Frontend                    │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ ResourcePanel │  │   地图主区域   │  │AnalysisBox│ │
│  │ (左侧悬浮窗)  │  │  MapView     │  │ (右侧收纳) │ │
│  │              │  │              │  │           │ │
│  │ • 搜索框     │  │ • 点击标点   │  │ • 拖拽排序 │ │
│  │ • 点位列表   │  │ • 输入备注   │  │ • 提交分析 │ │
│  │ • 标签筛选   │  │ • 飞入定位   │  │ • 结果展示 │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┘ │
│         │                  │                        │
│         ▼                  ▼                        │
│  ┌──────────────────────────────────────────────┐   │
│  │            Pinia Store (markersStore)         │   │
│  │  • 本地缓存 + 服务端同步                      │   │
│  │  • 乐观更新 (先更新 UI，后台同步)              │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────┘
                      │ REST API
                      ▼
┌─────────────────────────────────────────────────────┐
│                   后端 Backend                        │
│                                                     │
│  ┌──────────────┐  ┌────────────────┐              │
│  │ Marker CRUD  │  │ Tag Extractor  │              │
│  │ • POST 创建  │  │ • 规则匹配     │              │
│  │ • GET  列表  │  │ • 关键词提取   │              │
│  │ • PUT  更新  │  │ • NLP 分词     │              │
│  │ • DELETE 删除│  └────────────────┘              │
│  └──────┬───────┘                                    │
│         │ JSON 文件存储                              │
│         ▼                                            │
│  ~/.fde_markers.json          (每个 session 独立)     │
└─────────────────────────────────────────────────────┘
```

---

## 三、数据模型

### 3.1 Marker Schema

```python
class Marker(BaseModel):
    id: str            # uuid, 唯一标识
    name: str          # 点位名称（必填）
    lng: float         # 经度
    lat: float         # 纬度
    note: str = ""     # 备注文本
    tags: list[str] = []  # 自动生成的标签
    created_at: datetime
    updated_at: datetime
```

### 3.2 Tag Schema

```python
class TagInfo(BaseModel):
    tag: str           # 标签名
    count: int         # 该标签关联的点位数
```

### 3.3 标签类别体系

```
类别      子标签
──────────────────────────────────────
地理      城区/郊县/滨水/山区/平原
功能      商业/政务/居住/交通/教育/医疗/文旅/工业
规模     核心/次中心/边缘/独立
状态     已开发/建设期/规划中
风险     高人流/高风险/低密度
```

标签提取策略：先关键词匹配，无匹配时使用 jieba 分词取 top-3 名词。

---

## 四、API 设计

新增路由注册到 `agents/map_agent/routes.py`：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/markers` | 获取所有已保存点位 |
| `POST` | `/markers` | 创建点位（含备注，自动打标签） |
| `PUT` | `/markers/{id}` | 更新点位备注/名称 |
| `DELETE` | `/markers/{id}` | 删除点位 |
| `GET` | `/markers/tags` | 获取所有标签及其计数 |
| `GET` | `/markers?search=xxx` | 按名称搜索 |
| `GET` | `/markers?tag=xxx` | 按标签筛选 |

请求示例：

```json
POST /map/markers
{
  "name": "杭州东站",
  "lng": 120.213,
  "lat": 30.290,
  "note": "杭州东站是杭州市最大的高铁枢纽站，连接京沪高铁和宁杭高铁，日客流量约10万人次"
}

Response:
{
  "id": "a1b2c3d4",
  "name": "杭州东站",
  "lng": 120.213,
  "lat": 30.290,
  "note": "杭州东站是杭州市最大的高铁枢纽站，连接京沪高铁...",
  "tags": ["交通", "商业", "高人流", "城区"],
  "created_at": "2026-07-04T10:00:00Z"
}
```

---

## 五、前端组件

### 5.1 ResourcePanel.vue (新建)

```
┌─────────────────────────┐
│ 🔖 点位资源  [收起 ▲]    │  ← 与分析收纳盒一致的 header
├─────────────────────────┤
│ 🔍 搜索点位或标签...     │  ← 搜索框
├─────────────────────────┤
│   标签筛选:              │
│   [交通×] [商业×] [政务×] │  ← 可点击的标签 chip
├─────────────────────────┤
│ 📍 杭州东站           ✏️ │  ← 点击飞入地图，右侧编辑按钮
│ 🏷️ 交通 商业 高人流      │
│   连接京沪高铁和宁杭高铁 │  ← 截断备注
├─────────────────────────┤
│ 📍 省府大楼           ✏️ │
│ 🏷️ 政务 核心             │
│   浙江省人民政府所在地   │
├─────────────────────────┤
│ ...                     │
└─────────────────────────┘
```

- 样式复用 AnalysisBox（白色面板、圆角、阴影、玻璃效果）
- 位置：左侧，top: 60px, left: 12px
- 默认展开，可最小化
- 点击点位 → 地图 flyTo
- 点击编辑 → 弹窗修改备注
- 搜索即时过滤（客户端过滤）

### 5.2 MapView.vue (修改)

- 标点弹窗增加备注输入框（原来只有名称）
- 标记成功后自动 POST 到后端保存
- 已保存的点位从后端加载并渲染在地图上
- 地图加载时自动拉取 `/map/markers` 渲染已有点位

### 5.3 App.vue (修改)

- 新增 `<ResourcePanel />` 放在 map-area 左上角

### 5.4 markersStore (新建)

```typescript
// stores/markers.ts
interface MarkerData {
  id: string
  name: string
  lng: number
  lat: number
  note: string
  tags: string[]
  created_at: string
}

// State
markers: MarkerData[]
searchQuery: string
selectedTags: string[]

// Actions
fetchMarkers()          // GET /map/markers
createMarker(data)      // POST /map/markers
updateMarker(id, data)  // PUT /map/markers/{id}
deleteMarker(id)        // DELETE /map/markers/{id}
```

---

## 六、后端模块

### 6.1 `agents/map_agent/marker_store.py` (新建)

```python
class MarkerStore:
    """JSON 文件的点位持久化存储"""
    path: Path  # ~/.fde_markers.json
    
    def load_all() -> list[Marker]
    def create(marker) -> Marker
    def update(id, data) -> Marker
    def delete(id) -> bool
    def search(query: str) -> list[Marker]
```

### 6.2 `agents/map_agent/tag_extractor.py` (新建)

```python
class TagExtractor:
    """备注文本 → 标签"""
    
    # 规则匹配 (快速路径)
    KEYWORD_MAP = {
        "火车站|高铁|铁路|轨道": "交通",
        "地铁|公交|客运|枢纽": "交通", 
        "政府|省委|市委|办公厅": "政务",
        "商场|购物|商圈|商业街": "商业",
        "小区|住宅|楼盘|居民": "居住",
        "学校|大学|中学|小学": "教育",
        "医院|诊所|卫生院": "医疗",
        "工厂|园区|产业园": "工业",
        "景区|公园|景点|古镇": "文旅",
        "人口|人流|客流|人流量": "高人流",
        "风险|灾害|隐患": "风险",
        "核心|中心|中央": "核心",
        "在建|规划|待建": "建设期",
    }
    
    def extract(text: str) -> list[str]:
        # 1. 正则匹配关键词
        # 2. 未匹配到的词用 jieba 分词取 Top-3 名词
        # 3. 去重返回
```

---

## 七、文件清单（预计 9 个文件）

| 文件 | 操作 | 说明 |
|------|------|------|
| `agents/map_agent/models.py` | 修改 | 新增 Marker/TagInfo Schema |
| `agents/map_agent/marker_store.py` | 新建 | JSON 文件存储层 |
| `agents/map_agent/tag_extractor.py` | 新建 | 备注标签提取引擎 |
| `agents/map_agent/routes.py` | 修改 | 新增 5 个 marker 路由 |
| `frontend/map-ai/src/stores/markers.ts` | 新建 | Pinia 点位 Store |
| `frontend/map-ai/src/components/ResourcePanel.vue` | 新建 | 左侧资源面板 |
| `frontend/map-ai/src/components/MapView.vue` | 修改 | 备注输入 + 持久化联动 |
| `frontend/map-ai/src/App.vue` | 修改 | 挂载 ResourcePanel |
| `frontend/map-ai/src/style.css` | 修改 | 面板通用样式 |

---

## 八、实施步骤

```
Step 1 (1.5h): 后端 Marker CRUD + JSON 存储
  ├── models.py: Marker + TagInfo Schema
  ├── marker_store.py: load/save/search
  └── routes.py: 5 个 REST 端点

Step 2 (1h): 标签提取引擎
  ├── tag_extractor.py: 关键词匹配 + jieba 分词
  └── 集成到 POST /markers 创建流程

Step 3 (1.5h): 前端 Pinia Store + API 对接
  ├── markers.ts: fetch/create/update/delete
  └── MapView 对接 store

Step 4 (1.5h): ResourcePanel 面板组件
  ├── 搜索框 + 标签筛选
  ├── 点位列表渲染
  ├── 点击 flyTo 联动
  └── 编辑备注弹窗

Step 5 (0.5h): MapView 备注输入 + 自动保存
  └── 标点弹窗增加 textarea

Step 6 (0.5h): 回归测试 + 部署
  ├── 后端 pytest
  └── 前端 build → docker cp → nginx reload
```

---

## 九、技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 存储方式 | JSON 文件 | 数据量小（< 100条目），无需数据库 |
| 存储位置 | `~/.fde_markers.json` | 服务端持久化，不随部署丢失 |
| 标签提取 | 规则 + jieba | 规则快且准，jieba 兜底通用性 |
| 搜索方式 | 客户端过滤 | 数据量小，即时响应，无需网络请求 |
| 面板位置 | 左侧悬浮 | 右侧已有 AnalysisBox，左侧空白 |
| 面板样式 | 复用 AnalysisBox CSS | 保持 UI 一致性 |

---

## 十、测试计划

```
后端:
  ├── test_create_marker_with_tags      POST /markers
  ├── test_update_marker_note           PUT /markers/{id}
  ├── test_delete_marker                DELETE /markers/{id}
  ├── test_list_markers                 GET /markers
  ├── test_search_markers               GET /markers?search=高铁
  ├── test_filter_by_tag                GET /markers?tag=交通
  ├── test_tag_extraction               tag_extractor.extract(note)
  └── test_marker_persistence           stop/start backend, data persists

前端:
  └── 手动 E2E: 标点→输入备注→保存→刷新→验证
```