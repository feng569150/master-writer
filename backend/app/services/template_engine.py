"""
模板引擎
管理论文格式模板，支持 JSON 配置驱动
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from backend.app.models.schema import TemplateConfig, TemplateResponse
from backend.app.config import TEMPLATES_DIR
from backend.app.database import db
from backend.app.services.template_parser import TemplateParser


class TemplateEngine:
    """模板引擎：加载、管理、应用模板"""
    
    _templates: Dict[str, TemplateConfig] = {}
    DEFAULT_TEMPLATE: Dict[str, Any] = TemplateParser.get_default_template()
    
    @classmethod
    async def initialize(cls):
        """初始化：从文件加载内置模板到数据库，确保默认模板存在"""
        template_files = list(TEMPLATES_DIR.glob("*.json"))
        
        for tf in template_files:
            try:
                config = json.loads(tf.read_text(encoding="utf-8"))
                template_id = tf.stem
                
                # 检查是否已存在
                existing = await db.get_template(template_id)
                if not existing:
                    await db.create_template(
                        template_id=template_id,
                        name=config.get("name", template_id),
                        config=config,
                        is_builtin=True
                    )
            except Exception as e:
                print(f"加载模板失败 {tf}: {e}")
        
        # 确保默认模板存在
        if not await db.get_template("default"):
            await db.create_template(
                template_id="default",
                name=cls.DEFAULT_TEMPLATE["name"],
                config=cls.DEFAULT_TEMPLATE,
                is_builtin=True
            )
        
        # 加载到内存
        await cls.reload()
    
    @classmethod
    async def reload(cls):
        """重新加载所有模板到内存"""
        rows = await db.list_templates()
        cls._templates = {}
        for row in rows:
            try:
                config = row["config"]
                cls._templates[row["id"]] = TemplateConfig(**config)
            except Exception as e:
                print(f"解析模板失败 {row['id']}: {e}")
    
    @classmethod
    def get(cls, template_id: str) -> Optional[TemplateConfig]:
        """获取模板配置"""
        return cls._templates.get(template_id)
    
    @classmethod
    def list_all(cls) -> List[TemplateResponse]:
        """列出所有模板"""
        return [
            TemplateResponse(
                id=tid,
                name=config.name,
                description=config.description,
                is_builtin=True
            )
            for tid, config in cls._templates.items()
        ]
    
    @classmethod
    async def create_custom(cls, template_id: str, name: str, config: dict) -> TemplateConfig:
        """创建自定义模板"""
        if template_id in cls._templates:
            raise ValueError(f"模板 {template_id} 已存在")

        await db.create_template(template_id, name, config, is_builtin=False)
        template = TemplateConfig(**config)
        cls._templates[template_id] = template
        return template

    @classmethod
    async def delete_custom(cls, template_id: str):
        """删除自定义模板（内置模板禁止删除）"""
        template = cls._templates.get(template_id)
        if not template:
            raise ValueError(f"模板 {template_id} 不存在")
        try:
            await db.delete_template(template_id)
        except ValueError as e:
            raise e
        cls._templates.pop(template_id, None)

    @classmethod
    async def update_custom(cls, template_id: str, name: str, config: dict) -> TemplateConfig:
        """更新自定义模板（内置模板禁止修改）"""
        if template_id not in cls._templates:
            raise ValueError(f"模板 {template_id} 不存在")
        try:
            await db.update_template(template_id, name, config)
        except ValueError as e:
            raise e
        # 确保内存模板的 id/name 与传入一致
        merged = {**config, "id": template_id, "name": name}
        template = TemplateConfig(**merged)
        cls._templates[template_id] = template
        return template

    @classmethod
    async def list_raw(cls):
        """列出带内置标记的原始信息（用于前端管理）"""
        return await db.list_templates()


# 内置模板 JSON 文件内容（将由 create_templates 创建）
BUILTIN_TEMPLATES = {
    "bachelor_thesis": {
        "id": "bachelor_thesis",
        "name": "本科毕业论文",
        "description": "标准本科毕业论文格式（中文）",
        "page": {
            "width": 21.0,
            "height": 29.7,
            "margin_top": 2.54,
            "margin_bottom": 2.54,
            "margin_left": 3.17,
            "margin_right": 3.17
        },
        "fonts": {
            "chinese": "宋体",
            "english": "Times New Roman",
            "size": 12,
            "heading_font": "黑体",
            "heading_english": "Arial"
        },
        "paragraph": {
            "line_spacing": 1.5,
            "first_line_indent": 0.74,
            "space_before": 0,
            "space_after": 0,
            "alignment": "justify"
        },
        "headings": {
            "1": {
                "level": 1,
                "font": "黑体",
                "font_en": "Arial",
                "size": 16,
                "bold": True,
                "alignment": "center",
                "space_before": 24,
                "space_after": 12
            },
            "2": {
                "level": 2,
                "font": "黑体",
                "font_en": "Arial",
                "size": 14,
                "bold": True,
                "alignment": "left",
                "space_before": 18,
                "space_after": 6
            },
            "3": {
                "level": 3,
                "font": "黑体",
                "font_en": "Arial",
                "size": 12,
                "bold": True,
                "alignment": "left",
                "space_before": 12,
                "space_after": 6
            }
        },
        "supports_toc": True,
        "supports_abstract": True
    },
    "course_paper": {
        "id": "course_paper",
        "name": "课程论文",
        "description": "通用课程论文格式",
        "page": {
            "width": 21.0,
            "height": 29.7,
            "margin_top": 2.54,
            "margin_bottom": 2.54,
            "margin_left": 3.17,
            "margin_right": 3.17
        },
        "fonts": {
            "chinese": "宋体",
            "english": "Times New Roman",
            "size": 12,
            "heading_font": "黑体",
            "heading_english": "Arial"
        },
        "paragraph": {
            "line_spacing": 1.5,
            "first_line_indent": 0.74,
            "space_before": 0,
            "space_after": 0,
            "alignment": "justify"
        },
        "headings": {
            "1": {
                "level": 1,
                "font": "黑体",
                "font_en": "Arial",
                "size": 14,
                "bold": True,
                "alignment": "center",
                "space_before": 18,
                "space_after": 12
            },
            "2": {
                "level": 2,
                "font": "黑体",
                "font_en": "Arial",
                "size": 12,
                "bold": True,
                "alignment": "left",
                "space_before": 12,
                "space_after": 6
            }
        },
        "supports_toc": False,
        "supports_abstract": False
    }
}
