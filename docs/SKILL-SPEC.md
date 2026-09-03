# MasterWriter Skill 规范文档

## 1. Skill 概述

Skill 是 MasterWriter 的核心抽象，代表一个可复用的学术写作任务单元。每个 Skill 包含：
- 输入参数定义
- Prompt 模板
- 输出格式规范
- 模型调用参数

通过组合多个 Skill，可以完成从选题到成稿的完整论文写作流程。

---

## 2. Skill 文件格式

Skill 使用 YAML 格式定义，存放在 `backend/skills/` 目录下。

### 2.1 完整示例

```yaml
id: paper_outline
name: 论文大纲生成
description: 根据论文题目和类型生成结构化的三级大纲
version: "1.0"
category: preparation  # preparation | writing | polishing | tool

input:
  - name: topic
    type: string
    required: true
    description: 论文题目
  - name: paper_type
    type: string
    required: true
    default: bachelor_thesis
    description: 论文类型
    options: [bachelor_thesis, course_paper, literature_review]
  - name: word_count
    type: integer
    required: false
    default: 10000
    description: 预期总字数

context_vars:  # 会从全局上下文中自动读取的变量
  - outline  # 如果上下文中已有大纲，可用于参考

prompt_template: |
  你是一位资深的学术论文写作专家，擅长为{{paper_type}}生成严谨的结构化大纲。
  
  论文题目：{{topic}}
  预期字数：{{word_count}}字
  
  请生成一个三级大纲，要求：
  1. 逻辑清晰，层次分明
  2. 覆盖论文应有的完整结构
  3. 各部分字数分配合理
  4. 使用学术化的章节标题
  
  请严格按照以下 JSON 格式输出，不要输出其他内容：
  {
    "title": "论文标题",
    "sections": [
      {
        "level": 1,
        "title": "一级标题",
        "word_count": 预计字数,
        "children": [
          {
            "level": 2,
            "title": "二级标题",
            "word_count": 预计字数,
            "children": [
              {
                "level": 3,
                "title": "三级标题",
                "word_count": 预计字数
              }
            ]
          }
        ]
      }
    ]
  }

output:
  format: json
  schema:
    type: object
    properties:
      title:
        type: string
      sections:
        type: array
        items:
          type: object
          properties:
            level:
              type: integer
              enum: [1, 2, 3]
            title:
              type: string
            word_count:
              type: integer
            children:
              type: array
  
  auto_save: true        # 是否自动保存到数据库
  save_target: outline   # 保存到 paper 的哪个字段

model_params:
  temperature: 0.7
  max_tokens: 3000
  top_p: 0.9
```

---

## 3. Skill 字段规范

### 3.1 元数据字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | Skill 唯一标识，只能包含字母、数字、下划线 |
| name | string | 是 | 显示名称 |
| description | string | 是 | 功能描述 |
| version | string | 否 | 版本号，默认 "1.0" |
| category | string | 是 | 分类：preparation/writing/polishing/tool |
| tags | array | 否 | 标签列表 |

### 3.2 输入字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| input | array | 否 | 用户输入参数列表 |
| context_vars | array | 否 | 自动从上下文读取的变量 |

input 中每个参数：
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 参数名，用于模板变量插值 |
| type | string | 是 | 类型：string/int/float/boolean/enum |
| required | boolean | 是 | 是否必填 |
| default | any | 否 | 默认值 |
| description | string | 是 | 参数说明 |
| options | array | 否 | 枚举选项（type=enum 时必填） |

### 3.3 Prompt 模板

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| prompt_template | string | 是 | Prompt 模板，支持 Jinja2 语法 |
| system_prompt | string | 否 | 系统级 Prompt，追加在模板前 |

**变量插值规则**：
- `{{var_name}}` - 普通变量，会被 HTML 转义
- `{{var_name\|safe}}` - 原始变量，不转义
- 支持 Jinja2 的条件、循环等语法

### 3.4 输出配置

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| output.format | string | 是 | 输出格式：json/markdown/text |
| output.schema | object | 否 | JSON Schema（format=json 时建议提供） |
| output.auto_save | boolean | 否 | 是否自动保存到数据库，默认 false |
| output.save_target | string | 否 | 保存目标字段 |

### 3.5 模型参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model_params.temperature | float | 否 | 温度，默认 0.7 |
| model_params.max_tokens | integer | 否 | 最大 token 数 |
| model_params.top_p | float | 否 | Top P 采样 |
| model_params.model | string | 否 | 指定模型，默认使用用户配置 |

---

## 4. 内置 Skill 清单

### 4.1 准备阶段（preparation）

#### topic_analysis - 选题分析
分析论文选题的可行性、创新点和研究价值。

**输入**：
- topic: 论文题目
- field: 学科领域
- requirements: 学校/课程要求

**输出**：
```json
{
  "feasibility": "可行性分析...",
  "innovation_points": ["创新点1", "创新点2"],
  "research_value": "研究价值...",
  "suggested_approach": "建议的研究方法...",
  "potential_issues": ["可能的问题1"]
}
```

---

#### paper_outline - 大纲生成
生成论文的三级结构大纲。

**输入**：
- topic: 论文题目
- paper_type: 论文类型
- word_count: 预期字数

**输出**：三级大纲 JSON（见上方示例）

---

### 4.2 写作阶段（writing）

#### introduction - 引言写作
生成论文引言部分（研究背景、意义、现状、本文工作）。

**输入**：
- topic: 论文题目
- outline: 大纲（自动从上下文读取）
- word_count: 引言字数

**上下文依赖**：outline

**输出**：Markdown 格式的引言文本

---

#### literature_review - 文献综述
基于用户提供的参考文献生成文献综述。

**输入**：
- topic: 论文题目
- references: 参考文献列表（标题、作者、年份、摘要）
- word_count: 字数

**输出**：分类综述文本

---

#### body_writing - 正文写作
根据大纲节点生成正文段落。

**输入**：
- section_title: 当前章节标题
- section_outline: 当前章节大纲
- previous_sections: 前文内容摘要
- word_count: 字数

**上下文依赖**：outline, previous_sections

**输出**：Markdown 格式正文

---

#### conclusion - 结论写作
生成论文结论部分。

**输入**：
- topic: 论文题目
- main_findings: 主要发现（从上下文提取）
- outline: 大纲
- word_count: 字数

**上下文依赖**：outline, sections

**输出**：Markdown 格式结论

---

#### abstract - 摘要生成
基于全文生成中英文摘要。

**输入**：
- full_text: 论文全文
- word_count: 中文字数（通常 300-500）

**上下文依赖**：sections

**输出**：
```json
{
  "chinese": "中文摘要...",
  "english": "English abstract...",
  "keywords_zh": ["关键词1", "关键词2"],
  "keywords_en": ["keyword1", "keyword2"]
}
```

---

### 4.3 润色阶段（polishing）

#### polish - 段落润色
对指定段落进行学术化润色。

**输入**：
- text: 待润色文本
- style: 润色风格（学术/简洁/详细）

**输出**：润色后的文本 + 修改说明

---

#### reduce_similarity - 降重改写
对高相似度段落进行改写降重。

**输入**：
- text: 待降重文本
- similarity_text: 相似源文本
- target_similarity: 目标相似度

**输出**：改写后的文本

---

## 5. Skill 执行流程

### 5.1 单次执行流程
```
1. 用户请求执行 Skill
   ↓
2. SkillEngine 加载 Skill YAML
   ↓
3. 收集输入参数（用户输入 + 上下文变量）
   ↓
4. 渲染 Prompt 模板（Jinja2）
   ↓
5. 调用 ModelProvider 生成内容
   ↓
6. 解析输出（按 output.format）
   ↓
7. 如 auto_save=true，保存到数据库
   ↓
8. 更新全局上下文
   ↓
9. 返回结果给前端
```

### 5.2 Pipeline 执行流程
```
1. 用户定义 Pipeline：[skill1, skill2, skill3]
   ↓
2. 顺序执行每个 Skill
   ↓
3. 每个 Skill 的输出自动成为上下文的一部分
   ↓
4. 支持条件执行：if context.xxx then skill_y
   ↓
5. 全流程支持流式输出（SSE）
```

---

## 6. Skill 开发规范

### 6.1 Prompt 设计原则
1. **角色明确**：每个 Skill 的 Prompt 开头明确 AI 角色
2. **任务清晰**：具体说明要做什么，不要做什么
3. **格式强制**：要求严格的输出格式，减少解析失败
4. **示例引导**：复杂输出提供示例（few-shot）
5. **上下文注入**：通过变量将前文信息传递给当前 Skill

### 6.2 输出解析容错
- JSON 输出要求包裹在 ```json 代码块中
- 解析失败时返回原始文本，由前端处理
- 提供 schema 用于验证和补全

### 6.3 上下文管理
- Skill 通过 `context_vars` 声明依赖
- SkillEngine 自动注入上下文变量到模板
- 执行后自动将输出写入上下文
- 上下文在内存中维护，定期持久化到数据库

---

## 7. 自定义 Skill 示例

### 7.1 自定义课程论文大纲 Skill

```yaml
id: course_outline
name: 课程论文大纲
description: 针对课程论文的快速大纲生成
category: preparation

input:
  - name: course_name
    type: string
    required: true
    description: 课程名称
  - name: topic
    type: string
    required: true
    description: 论文主题

prompt_template: |
  你是一位{{course_name}}课程的助教，帮助学生生成课程论文大纲。
  
  课程：{{course_name}}
  主题：{{topic}}
  
  课程论文要求：
  - 字数：3000-5000字
  - 结构：引言、主体（2-3个论点）、结论
  - 风格：学术但不需要过于深入
  
  请生成二级大纲：
  
  输出格式：
  {
    "sections": [
      {"level": 1, "title": "标题", "children": [
        {"level": 2, "title": "子标题"}
      ]}
    ]
  }

output:
  format: json
  auto_save: true
  save_target: outline

model_params:
  temperature: 0.8
  max_tokens: 1500
```

### 7.2 注册自定义 Skill
1. 将 YAML 文件放入 `backend/skills/` 目录
2. 重启后端服务（或调用热加载接口）
3. 前端自动显示新 Skill
