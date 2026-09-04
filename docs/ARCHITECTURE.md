# MasterWriter 架构设计文档

## 1. 设计哲学

### 1.1 极简主义
- **零构建前端**：不引入 React/Vue 构建步骤，直接用 HTML+JS+Tailwind CDN
- **单文件启动**：一个 `start.py` 搞定所有启动逻辑
- **约定优于配置**：开箱即用，80% 用户无需修改配置

### 1.2 性能优先
- **异步全链路**：FastAPI 原生异步，AI 调用流式响应
- **本地计算优先**：查重、格式处理全部本地完成
- **最小依赖**：Python 依赖控制在 20 个以内

### 1.3 可扩展性
- **Skill 即插件**：新增写作功能只需添加 YAML 文件
- **模板数据驱动**：JSON 配置驱动文档格式，无需改代码
- **模型 Provider 抽象**：新增 AI 模型只需实现统一接口

---

## 2. 核心模块设计

### 2.1 模板引擎（TemplateEngine）

职责：管理论文格式模板，生成符合规范的 Word 文档。

```python
class TemplateEngine:
    def load_template(template_id: str) -> TemplateConfig
    def apply_style(paragraph, style_config: StyleConfig)
    def generate_document(content: PaperContent, template: TemplateConfig) -> Document
```

**关键设计**：
- 模板配置是纯 JSON，支持所有 python-docx 可设置的样式属性
- 文档生成采用"内容+样式分离"模式：先写入纯文本内容，再批量应用样式
- 目录自动生成：通过 python-docx 的 TOC 字段

### 2.2 Skill 引擎与 Pipeline 编排

职责：解析 Skill 定义（YAML），按 Pipeline 编排执行，产出论文内容。

```python
class WritingAgent:
    async def load():            # 论文状态 ← 数据库（title/outline/sections）
    async def run_skill(...)     # 执行单个 Skill
    async def run_pipeline(...)  # 按 steps 顺序执行（skill / loop）
    async def save():            # 状态 → 数据库
```

**Pipeline 定义（数据驱动，内置或用户自定义）**：
```json
{"steps": [
  {"skill": "paper_outline", "save_to": "outline"},
  {"loop": {"over": "outline.sections", "as": "section",
     "steps": [{"skill": "body_writing", "save_to": "sections"}]}},
  {"skill": "abstract", "save_to": "abstract"}
]}
```

**关键设计**：
- 论文状态即"记忆"：每篇论文的 title/outline/sections 就是完整上下文，
  每次执行从数据库读取、步骤间更新、结束写回，无需额外缓存层
- 变量插值：`{{title}}`、`{{outline.sections}}`、`{{section.title}}`
- 内置 3 个 pipeline（一键成文/仅大纲/全文润色），用户可自定义 pipeline 存数据库
- 步骤类型只保留 skill 与 loop（按需取舍，不做 unused 的条件分支）
- Skill 定义用 YAML：输入参数、输出格式、Prompt 模板、模型参数

### 2.3 模型提供者（ModelProvider）

职责：统一封装各种 AI 模型的调用接口。

```python
class ModelProvider(ABC):
    @abstractmethod
    async def chat(messages: List[Message], **params) -> AsyncGenerator[str, None]
    
    @abstractmethod
    def validate_config(config: ModelConfig) -> bool

class OpenAIProvider(ModelProvider): ...
class ZhipuProvider(ModelProvider): ...
class OllamaProvider(ModelProvider): ...
class DeepSeekProvider(ModelProvider): ...
```

**关键设计**：
- 所有 Provider 返回统一格式的流式输出（SSE）
- 支持任意 OpenAI 兼容端点（中转站/通义/Kimi 等自定义 base_url）
- 流式 chunk 容错：空 choices / 用法统计块 / error 块不崩溃
- 配置持久化到数据库，重启不丢

### 2.4 查重引擎（PlagiarismEngine）

职责：本地文本查重，生成相似度报告。

```python
class PlagiarismEngine:
    def fingerprint(text: str) -> Fingerprint
    def index_document(doc_id: str, text: str)
    def check(text: str, threshold: float = 0.3) -> CheckResult
    def add_to_library(doc_id: str, text: str, metadata: dict)
```

**算法选择**：
- **SimHash**：用于快速初筛，判断两段文本是否可能相似（海明距离 < 3）
- **MinHash + LSH**：用于大规模文档库的近似最近邻查找
- **细粒度比对**：对初筛出的候选文档，使用滑动窗口 + 编辑距离进行精确比对

**为什么不用纯 SimHash？**
- SimHash 适合判断"是否相似"，但不适合找出"具体哪里相似"
- 组合方案：MinHash 做库级初筛 -> SimHash 做段落级过滤 -> 滑动窗口做句子级精确匹配

### 2.5 文档引擎（DocumentEngine）

职责：内容到文档的转换，支持多种导出格式。

```python
class DocumentEngine:
    def to_docx(content: PaperContent, template: TemplateConfig) -> bytes
    def to_pdf(docx_bytes: bytes) -> bytes  # 依赖 libreoffice
    def to_markdown(content: PaperContent) -> str
```

---

## 3. 数据模型

### 3.1 核心实体

```python
# 论文项目
class Paper(BaseModel):
    id: str
    title: str
    template_id: str
    outline: Outline
    sections: List[Section]
    created_at: datetime
    updated_at: datetime

# 论文段落
class Section(BaseModel):
    id: str
    paper_id: str
    type: str  # introduction, body, conclusion, etc.
    title: str
    content: str
    order: int

# 模板配置
class TemplateConfig(BaseModel):
    id: str
    name: str
    page: PageConfig
    fonts: FontConfig
    paragraph: ParagraphConfig
    headings: Dict[str, HeadingConfig]

# 查重指纹
class Fingerprint(BaseModel):
    doc_id: str
    simhash: int
    minhash: List[int]
    chunks: List[ChunkFingerprint]
```

### 3.2 数据库 Schema（SQLite）

```sql
-- 论文表
CREATE TABLE papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    template_id TEXT NOT NULL,
    outline TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 论文章节表
CREATE TABLE sections (
    id TEXT PRIMARY KEY,
    paper_id TEXT REFERENCES papers(id),
    type TEXT NOT NULL,
    title TEXT,
    content TEXT,
    "order" INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 模板表
CREATE TABLE templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config TEXT NOT NULL,  -- JSON
    is_builtin INTEGER DEFAULT 0
);

-- 查重库文档表
CREATE TABLE paper_library (
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,
    fingerprint TEXT,  -- JSON
    metadata TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 用户配置表
CREATE TABLE user_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## 4. API 设计

### 4.1 模板 API
```
GET  /api/templates              # 获取所有模板
GET  /api/templates/{id}         # 获取模板详情
POST /api/templates              # 创建自定义模板
```

### 4.2 写作 API
```
POST /api/papers                 # 创建论文项目
GET  /api/papers/{id}            # 获取论文
PUT  /api/papers/{id}            # 更新论文

POST /api/skills/{id}/execute    # 执行单个 Skill
POST /api/skills/pipeline        # 执行 Skill Pipeline
     Body: { paper_id, skills: ["outline", "introduction", ...] }
     Response: SSE Stream

POST /api/generate               # 通用 AI 生成接口
     Body: { messages, model, stream }
     Response: SSE Stream
```

### 4.3 查重 API
```
POST /api/plagiarism/check       # 查重
     Body: { text, threshold }
     Response: { similarity, matches: [...] }

POST /api/plagiarism/library     # 添加到查重库
GET  /api/plagiarism/library     # 获取查重库列表
DELETE /api/plagiarism/library/{id}  # 删除
```

### 4.4 导出 API
```
POST /api/export/docx            # 导出 Word
POST /api/export/pdf             # 导出 PDF
POST /api/export/markdown        # 导出 Markdown
```

---

## 5. 前端架构

### 5.1 技术选择理由
**为什么不用 React/Vue？**
- 项目规模不大，不需要组件化框架的复杂度
- 零构建 = 零等待，用户克隆即用
- TailwindCSS CDN 提供足够的设计系统
- Vanilla JS 配合 Custom Elements 足以实现组件化

### 5.2 前端模块
```javascript
// api.js - 统一 API 调用，封装 SSE 处理
// app.js - 应用状态管理（全局 Store）
// editor.js - Markdown 编辑器封装
// components.js - UI 组件（对话框、通知、加载态）
// template.js - 模板选择与管理
// writing.js - 写作工作台逻辑
// plagiarism.js - 查重界面逻辑
```

### 5.3 状态管理
采用简单的全局 Store 模式（非 Redux，纯对象+事件）：
```javascript
const store = {
    state: { paper: null, template: null, sections: [] },
    listeners: [],
    setState(newState) { this.state = { ...this.state, ...newState }; this.notify(); },
    subscribe(fn) { this.listeners.push(fn); },
    notify() { this.listeners.forEach(fn => fn(this.state)); }
};
```

---

## 6. 安全设计

### 6.1 数据安全
- 所有数据存储在项目目录的 `data/` 文件夹下
- API Key 使用 Fernet 对称加密存储，密钥派生自机器指纹
- 不上传任何数据到外部（除 AI 模型 API 调用外）

### 6.2 访问控制
- 本地运行，默认无认证（单用户场景）
- 可选开启简单密码保护（后续扩展）

---

## 7. 性能优化策略

### 7.1 启动优化
- 使用 `uvicorn` 的 `--reload` 仅开发环境
- 前端资源全部内联或 CDN，零加载等待
- SQLite 数据库延迟初始化

### 7.2 运行时优化
- AI 生成采用 SSE 流式输出，首字响应 < 2s
- 查重使用多线程：指纹提取并行化
- 文档生成异步执行，不阻塞主线程

### 7.3 存储优化
- 论文内容分章节存储，避免单条记录过大
- 查重指纹预计算，增量更新
- 定期压缩历史版本（后续）
