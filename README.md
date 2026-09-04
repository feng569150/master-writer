# MasterWriter - 智能论文写作助手

本地运行的 Web 端学术写作智能体，专注于毕业论文、课程论文等固定格式文档的高质量生成与格式化导出。

## ✨ 核心特性

- **📄 格式标准化** —— 内置模板 + 上传 Word 解析 + 手动定义模板，生成即合规
- **🧠 结构化写作** —— Skill 系统将论文拆解为选题→大纲→引言→正文→结论→摘要，分步生成
- **⚡ 一键成文** —— 大纲→全文→摘要→参考文献全自动生成，支持暂停保留已生成内容
- **⚡ 极速响应** —— 本地运行，流式输出，无需等待
- **🔧 多模型支持** —— OpenAI 兼容端点（OpenAI/智谱/DeepSeek/中转站/自定义）+ Ollama + 本地 Mock

## 🚀 快速开始

### 环境要求
- Python 3.10+
- Windows / macOS / Linux

### 安装运行

```bash
# 克隆项目
git clone <项目地址>
cd master-writer

# 一键启动（自动安装依赖）
python start.py
```

或者手动安装：

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 启动服务
python start.py
```

启动后自动打开浏览器访问 `http://127.0.0.1:8765`

## 📁 项目结构

```
master-writer/
├── docs/                       # 文档
│   ├── PRD-v1.md              # 需求文档
│   ├── ARCHITECTURE.md        # 架构设计
│   └── SKILL-SPEC.md          # Skill 规范
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # SQLite 数据库
│   │   ├── models/
│   │   │   └── schema.py      # 数据模型
│   │   ├── routers/
│   │   │   ├── template.py    # 模板路由
│   │   │   ├── writing.py     # 写作路由
│   │   │   ├── export.py      # 导出路由
│   │   │   └── config.py      # 模型配置路由
│   │   └── services/
│   │       ├── template_engine.py    # 模板引擎
│   │       ├── template_parser.py    # Word 模板解析
│   │       ├── document_engine.py    # 文档引擎
│   │       ├── skill_engine.py       # Skill 引擎
│   │       └── model_provider.py     # 模型提供者
│   ├── skills/                # 内置 Skill
│   │   ├── topic_analysis.yaml
│   │   ├── paper_outline.yaml
│   │   ├── introduction.yaml
│   │   ├── body_writing.yaml
│   │   ├── conclusion.yaml
│   │   ├── abstract.yaml
│   │   ├── polish.yaml
│   │   └── reduce_similarity.yaml
│   ├── templates/             # 文档模板配置
│   │   ├── bachelor_thesis.json
│   │   └── course_paper.json
│   └── requirements.txt
├── frontend/
│   ├── index.html             # 主页面
│   ├── css/style.css          # 样式
│   └── js/app.js              # 前端逻辑
├── data/                      # 运行时数据（自动创建）
│   └── db.sqlite             # SQLite 数据库
├── start.py                   # 一键启动脚本
└── README.md
```

## 📝 使用指南

### 1. 配置 AI 模型

首次使用需要配置 AI 模型：
- 点击右上角「设置」
- 选择模型提供者（OpenAI / 智谱 / DeepSeek / Ollama）
- 输入 API Key（本地 Ollama 无需 Key）

### 2. 创建论文

- 点击「新建论文」
- 输入论文题目
- 选择模板（本科毕业论文 / 课程论文）

### 3. 分步写作

在写作工作台：
1. 点击「生成大纲」—— AI 根据题目生成三级大纲
2. 点击「写引言」—— 生成研究背景和意义
3. 点击「写正文」—— 分章节生成内容
4. 点击「写结论」—— 生成总结和展望
5. 点击「生成摘要」—— 基于全文生成中英文摘要
6. 点击「参考文献」—— 生成 GB/T 7714 格式文献列表

### 4. 一键成文

- 点击「一键成文」自动完成：大纲 → 各章正文 → 摘要 → 参考文献
- 生成过程中可点「暂停」，已生成内容自动保存为章节

### 5. 模板管理

- 「我的论文」→「模板管理」：上传 Word 解析 / 手动定义 / 编辑 / 删除
- 内置模板（默认/本科毕业论文/课程论文）受保护不可删改

### 6. 导出

- 在写作页面点击「导出 Word」或「导出 MD」
- Word 导出自动应用模板格式（字体、行距、标题样式、自动目录、参考文献规范）

## 🔧 技术架构

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | HTML5 + TailwindCSS + Vanilla JS | 零构建步骤，克隆即用 |
| 后端 | FastAPI + Uvicorn | 异步高性能 |
| Agent | Memory + Planner + Executor + Loop | 轻量级上下文管理、Skill 编排、Agent Loop |
| 数据库 | SQLite + aiosqlite | 本地存储，无需配置 |
| 文档 | python-docx | Word 生成（TOC、标题样式、摘要、参考文献） |
| 模型 | OpenAI 兼容层 + Ollama + Mock | 多模型统一接口，无 Key 可 Mock 演示 |

## 🧪 测试

```bash
# 单元测试（模板/文档/Agent 编排/模型解析）
python -m unittest discover -s tests

# 端到端 API 测试（需先启动服务）
python backend/app/main.py
python tests/e2e_api.py
```

## 📝 开发计划

- [x] Phase 1：基础骨架
  - [x] 项目结构搭建
  - [x] FastAPI 基础服务
  - [x] 前端基础界面
  - [x] SQLite 数据库初始化
- [x] Phase 2：模板与文档引擎
  - [x] Word 模板上传解析
  - [x] 默认模板（主流论文格式）
  - [x] Word 导出（TOC/摘要/标题样式/参考文献）
- [x] Phase 3：Agent 写作系统
  - [x] 记忆系统（Memory）
  - [x] Skill 编排（Pipeline/Loop）
  - [x] Agent Loop（规划-执行-反思）
  - [x] 一键成文 + 暂停保留
  - [x] Mock 模式（无 Key 可演示全流程）
- [x] Phase 4：模板体系完善
  - [x] 手动定义模板（部分填写自动补全）
  - [x] 模板编辑/删除（内置保护）
  - [x] 自定义 OpenAI 兼容端点 + 连接测试
- [x] Phase 5：测试
  - [x] 30 个单元测试全部通过
  - [x] 端到端 API 流程验证通过

## 📄 License

MIT License
