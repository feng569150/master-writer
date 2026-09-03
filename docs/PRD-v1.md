# MasterWriter 需求文档 v1.0

## 1. 产品概述

MasterWriter 是一个本地运行的 Web 端学术写作智能体，专注于毕业论文、课程论文等固定格式文档的高质量生成与处理。

### 1.1 目标用户
- 本科生、研究生
- 需要频繁撰写固定格式课程论文的学生
- 对格式规范敏感、对查重成本敏感的用户

### 1.2 核心价值
- **零格式焦虑**：选择模板后，生成的文档自动符合格式规范
- **高质量生成**：通过结构化 Skill 引导 AI 分步写作，而非一次性生成
- **零成本查重**：本地语义查重引擎，不依赖第三方服务
- **极速响应**：本地运行，无网络延迟（除 AI 模型调用外）

---

## 2. 功能需求

### 2.1 模板系统（Template Engine）
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 预设模板 | 本科毕业论文、课程论文、文献综述 | P0 |
| 模板配置 | 字体、字号、行距、页边距、标题样式 | P0 |
| 自定义模板 | 用户可保存自己的模板配置 | P1 |
| 模板市场 | 常见高校模板预设（后续扩展） | P2 |

**格式维度**：
- 页面：A4, 页边距（上下左右）
- 字体：中文字体、英文字体、标题字体
- 段落：行距（固定值/倍数）、首行缩进、段前段后
- 标题：多级标题样式（一级、二级、三级）
- 其他：页眉页脚、页码、目录自动生成

### 2.2 写作系统（Writing Engine）
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 分步写作 | 通过 Skill 将论文拆解为：选题→大纲→引言→正文→结论→摘要 | P0 |
| 上下文记忆 | 维护论文全局状态，确保前后一致 | P0 |
| 引用管理 | 支持插入参考文献，自动生成引用列表 | P1 |
| 多模型支持 | OpenAI、智谱、本地 Ollama、DeepSeek 等 | P0 |
| 续写/改写 | 对选中段落进行续写、润色、降重 | P1 |

### 2.3 查重系统（Plagiarism Engine）
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 本地查重 | 基于 SimHash + MinHash 的文本指纹比对 | P0 |
| 本地库 | 用户可上传自己的论文库作为比对源 | P0 |
| 互联网库 | 可选：接入免费搜索引擎片段比对（后续） | P2 |
| 查重报告 | 高亮重复段落，显示相似度、来源 | P0 |
| 降重建议 | 对重复段落给出 AI 降重建议 | P1 |

### 2.4 导出系统
| 功能 | 说明 | 优先级 |
|------|------|--------|
| Word 导出 | .docx 格式，完全保留样式 | P0 |
| PDF 导出 | 通过 libreoffice 或 weasyprint 转换 | P1 |
| Markdown 导出 | 便于版本管理 | P1 |

---

## 3. 非功能需求

### 3.1 性能
- 启动时间 < 3 秒
- 页面切换 < 100ms
- AI 生成首字响应 < 2 秒（流式输出）
- 查重 1 万字 < 5 秒（本地库 100 篇）

### 3.2 可用性
- 单命令启动：`python main.py` 或双击脚本
- 无需配置即可使用基础功能
- 前端界面简洁，核心功能 3 步内可达

### 3.3 可扩展性
- Skill 系统插件化，可热加载
- 模板系统数据驱动，新增模板无需改代码
- 模型 Provider 可插拔

### 3.4 安全
- 所有数据本地存储（SQLite）
- API Key 本地加密存储
- 不上传用户论文到云端

---

## 4. 技术架构

### 4.1 技术栈
- **后端**：Python 3.10+, FastAPI, Uvicorn
- **前端**：原生 HTML5 + TailwindCSS + Vanilla JS（零构建步骤）
- **数据库**：SQLite（用户配置、论文库、查重索引）
- **文档**：python-docx, mammoth
- **查重**：simhash, datasketch(MinHash)
- **AI 调用**：OpenAI SDK 兼容层 + HTTP 客户端

### 4.2 架构图
```
┌─────────────────────────────────────────────┐
│                Browser (Frontend)            │
│   Vanilla JS + Tailwind + Marked.js         │
└──────────────────┬──────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────┐
│              FastAPI Server                  │
│  ┌──────────┬──────────┬──────────┐         │
│  │ Template │ Writing  │Plagiarism│         │
│  │ Router   │ Router   │ Router   │         │
│  └────┬─────┴────┬─────┴────┬─────┘         │
│       │          │          │               │
│  ┌────▼─────┐ ┌──▼───┐ ┌────▼────┐         │
│  │Template  │ │Skill │ │SimHash  │         │
│  │Engine    │ │Engine│ │Engine   │         │
│  └──────────┘ └──────┘ └─────────┘         │
│  ┌──────────┬──────────┬──────────┐         │
│  │  Model   │ Document │  SQLite  │         │
│  │ Provider │  Engine  │  Store   │         │
│  └──────────┴──────────┴──────────┘         │
└─────────────────────────────────────────────┘
```

### 4.3 数据流
1. 用户选择模板 → 加载模板配置 → 渲染写作界面
2. 用户输入需求 → Skill Engine 拆解任务 → Model Provider 生成 → 保存到 SQLite
3. 用户点击查重 → 提取文本指纹 → 比对本地库 → 生成报告 → 高亮显示
4. 用户导出 → Document Engine 应用模板样式 → 生成 .docx

---

## 5. Skill 系统设计

Skill 是 MasterWriter 的核心抽象，每个 Skill 是一个可复用的写作任务单元。

### 5.1 Skill 定义
```yaml
skill:
  id: paper_outline
  name: 论文大纲生成
  description: 根据选题生成三级论文大纲
  input:
    - topic: 论文题目
    - type: 论文类型（本科/课程）
    - word_count: 预期字数
  output:
    format: json
    schema:
      outline: array  # 三级大纲结构
  prompt_template: |
    你是一位资深的学术论文写作专家...
  model_params:
    temperature: 0.7
    max_tokens: 2000
```

### 5.2 内置 Skill 列表
| Skill ID | 名称 | 阶段 |
|----------|------|------|
| topic_analysis | 选题分析 | 准备 |
| paper_outline | 大纲生成 | 准备 |
| introduction | 引言写作 | 写作 |
| literature_review | 文献综述 | 写作 |
| methodology | 研究方法 | 写作 |
| body_writing | 正文写作 | 写作 |
| conclusion | 结论写作 | 写作 |
| abstract | 摘要生成 | 收尾 |
| keywords | 关键词提取 | 收尾 |
| polish | 段落润色 | 工具 |
| reduce_similarity | 降重改写 | 工具 |

### 5.3 Skill 编排
支持 Skill Pipeline：
```
topic_analysis -> paper_outline -> introduction -> body_writing -> conclusion -> abstract
```

---

## 6. 开发周期

### Phase 1：基础骨架 ✅
- [x] 项目结构搭建
- [x] FastAPI 基础服务
- [x] 前端基础界面（Tailwind）
- [x] SQLite 数据库初始化

### Phase 2：模板与文档引擎 ✅
- [x] 模板配置系统
- [x] Word 模板上传解析（python-docx）
- [x] 默认模板（主流论文格式）
- [x] Word 导出（TOC 域、摘要、标题样式）

### Phase 3：写作系统 ✅
- [x] Agent 记忆系统（PaperMemory + MemoryStore）
- [x] 模型 Provider 抽象层（含 Mock 模式）
- [x] Skill 编排（Pipeline / Loop / 变量插值）
- [x] Agent Loop（Observe→Plan→Execute→Reflect）
- [x] 流式生成接口（SSE）
- [x] 写作工作台界面

### Phase 4：查重系统 ✅
- [x] SimHash + MinHash 指纹提取
- [x] 本地论文库管理
- [x] 查重比对算法
- [x] 查重报告生成
- [x] 第三方查重 API 插槽（PaperPass 等）
- [x] 前端查重界面

### Phase 5：完善与测试 ✅
- [x] 所有内置 Skill 实现（8 个）
- [x] 降重/润色功能
- [x] 16 个单元测试全部通过
- [x] 端到端 API 流程验证
- [x] 性能优化（流式输出、异步 SQLite）
- [x] 一键启动脚本（自动装依赖、开浏览器）

---

## 7. 项目目录结构

```
master-writer/
├── docs/                       # 文档
│   ├── PRD-v1.md
│   ├── ARCHITECTURE.md
│   └── SKILL-SPEC.md
├── backend/                    # 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI 入口
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # SQLite ORM
│   │   ├── routers/
│   │   │   ├── template.py
│   │   │   ├── writing.py
│   │   │   ├── plagiarism.py
│   │   │   └── export.py
│   │   ├── services/
│   │   │   ├── template_engine.py
│   │   │   ├── document_engine.py
│   │   │   ├── skill_engine.py
│   │   │   ├── model_provider.py
│   │   │   └── plagiarism_engine.py
│   │   └── models/
│   │       ├── schema.py       # Pydantic 模型
│   │       └── entities.py     # 数据库实体
│   ├── skills/                 # Skill 定义
│   │   ├── __init__.py
│   │   ├── topic_analysis.yaml
│   │   ├── paper_outline.yaml
│   │   ├── introduction.yaml
│   │   ├── body_writing.yaml
│   │   ├── conclusion.yaml
│   │   ├── abstract.yaml
│   │   └── polish.yaml
│   ├── templates/              # 文档模板配置
│   │   ├── bachelor_thesis.json
│   │   └── course_paper.json
│   ├── requirements.txt
│   └── run.py                  # 启动脚本
├── frontend/                   # 前端
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── api.js
│       ├── editor.js
│       └── components.js
├── tests/                      # 测试
│   ├── test_template.py
│   ├── test_skill.py
│   └── test_plagiarism.py
├── scripts/
│   └── setup.bat               # Windows 一键安装
├── data/                       # 运行时数据（gitignore）
│   ├── db.sqlite
│   └── paper_library/
├── README.md
└── start.py                    # 一键启动
```

---

## 8. 界面原型

### 8.1 主界面布局
```
┌─────────────────────────────────────────────────────┐
│  MasterWriter                      [设置] [帮助]    │
├──────────┬──────────────────────────────────────────┤
│          │  模板：本科毕业论文 ▼                    │
│  导航    │  ─────────────────────────────────────   │
│  ─────   │                                          │
│  工作台  │  论文题目：____________________          │
│  大纲    │                                          │
│  写作    │  [生成大纲]                              │
│  查重    │                                          │
│  导出    │  大纲编辑器                              │
│          │  ├── 1. 绪论                             │
│          │  │   ├── 1.1 研究背景                   │
│          │  │   └── 1.2 研究意义                   │
│          │  ├── 2. 文献综述                         │
│          │  └── 3. ...                            │
│          │                                          │
│          │  [生成引言] [生成正文] [生成结论]        │
│          │                                          │
│          │  ┌─────────────────────────────────┐     │
│          │  │  编辑区（Markdown 所见即所得）   │     │
│          │  │                                 │     │
│          │  └─────────────────────────────────┘     │
│          │                                          │
│          │  [查重] [导出 Word]                      │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
```

### 8.2 查重报告界面
```
┌─────────────────────────────────────────────────────┐
│  查重报告                              相似度：12.5% │
├─────────────────────────────────────────────────────┤
│  [文本区域]                                          │
│  这段文字与《xxx论文》相似度 85%  ▲                  │
│  ┌─────────────────────────────────────────────┐    │
│  │  高亮显示的重复段落...                       │    │
│  └─────────────────────────────────────────────┘    │
│  [AI 降重建议]                                       │
│  ┌─────────────────────────────────────────────┐    │
│  │  改写后的文本...                             │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## 9. 风险与对策

| 风险 | 对策 |
|------|------|
| AI 生成质量不稳定 | Skill 细化 + 人工编辑 + 多轮优化 |
| 本地查重准确率不如商业产品 | 明确产品定位（辅助工具），算法持续优化 |
| 模板无法覆盖所有学校 | 提供自定义模板 + 社区贡献机制 |
| Word 格式兼容性 | 基于 python-docx 标准库，测试多版本 Word |

---

## 10. 成功指标

- 从启动到写出第一篇符合格式的论文 < 30 分钟
- 格式问题投诉率为 0（模板化生成）
- 查重功能零成本运行
- 用户满意度 ≥ 4.5/5
