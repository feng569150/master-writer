"""
Pydantic 数据模型
定义所有 API 的请求/响应格式
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


# ==================== 通用 ====================

class ResponseBase(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[Any] = None


# ==================== 模板 ====================

class PageConfig(BaseModel):
    width: float = 21.0  # cm
    height: float = 29.7  # cm
    margin_top: float = 2.54  # cm
    margin_bottom: float = 2.54
    margin_left: float = 3.17
    margin_right: float = 3.17


class FontConfig(BaseModel):
    chinese: str = "宋体"
    english: str = "Times New Roman"
    size: float = 12.0  # 磅（支持 10.5 等五号字）
    heading_font: str = "黑体"
    heading_english: str = "Arial"


class ParagraphConfig(BaseModel):
    line_spacing: float = 1.5  # 倍行距
    first_line_indent: float = 0.74  # cm (约2字符)
    space_before: float = 0
    space_after: float = 0
    alignment: str = "justify"  # left/right/center/justify


class HeadingConfig(BaseModel):
    level: int
    font: str
    font_en: str
    size: float
    bold: bool = True
    alignment: str = "left"
    space_before: float = 12  # pt
    space_after: float = 6


class TemplateConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    page: PageConfig = Field(default_factory=PageConfig)
    fonts: FontConfig = Field(default_factory=FontConfig)
    paragraph: ParagraphConfig = Field(default_factory=ParagraphConfig)
    headings: Dict[str, HeadingConfig] = Field(default_factory=dict)
    supports_toc: bool = True  # 是否自动生成目录
    supports_abstract: bool = True


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    is_builtin: bool = True


# ==================== 论文 ====================

class OutlineNode(BaseModel):
    level: int = Field(ge=1, le=3)
    title: str
    word_count: Optional[int] = None
    children: List["OutlineNode"] = Field(default_factory=list)


OutlineNode.model_rebuild()


class PaperCreate(BaseModel):
    title: str
    template_id: str


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    outline: Optional[dict] = None
    content: Optional[str] = None


class PaperResponse(BaseModel):
    id: str
    title: str
    template_id: str
    outline: Optional[dict] = None
    created_at: str
    updated_at: str


class SectionCreate(BaseModel):
    paper_id: str
    type: str
    title: str = ""
    content: str = ""
    order: int = 0


class SectionUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None


class SectionResponse(BaseModel):
    id: str
    paper_id: str
    type: str
    title: str
    content: str
    order: int


# ==================== Skill ====================

class SkillInput(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    default: Optional[Any] = None
    description: str = ""
    options: Optional[List[str]] = None


class SkillOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), populate_by_name=True)
    format: Literal["json", "markdown", "text"] = "text"
    output_schema: Optional[Dict[str, Any]] = Field(None, alias="schema")
    auto_save: bool = False
    save_target: Optional[str] = None


class SkillDefinition(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: str
    name: str
    description: str
    version: str = "1.0"
    category: Literal["preparation", "writing", "polishing", "tool"]
    input: List[SkillInput] = Field(default_factory=list)
    context_vars: List[str] = Field(default_factory=list)
    prompt_template: str
    system_prompt: Optional[str] = None
    output: SkillOutput
    model_params: Dict[str, Any] = Field(default_factory=dict)


class SkillExecuteRequest(BaseModel):
    paper_id: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = True


class SkillPipelineRequest(BaseModel):
    paper_id: str
    skills: List[str]


# ==================== AI 生成 ====================

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class GenerateRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    provider: Optional[str] = None
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ModelConfig(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str


# ==================== 导出 ====================

class ExportRequest(BaseModel):
    paper_id: str
    format: Literal["docx", "pdf", "markdown"] = "docx"
