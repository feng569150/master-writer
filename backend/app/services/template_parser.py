"""
模板解析器
从用户上传的 Word 文档中解析格式模板
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from backend.app.models.schema import TemplateConfig, PageConfig, FontConfig, ParagraphConfig, HeadingConfig


class TemplateParser:
    """Word 模板解析器"""
    
    @classmethod
    def parse_docx(cls, file_path: str) -> Dict[str, Any]:
        """解析 Word 文档为模板配置"""
        doc = Document(file_path)
        
        config = {
            "id": "custom",
            "name": "自定义模板",
            "description": "从上传文档解析的模板",
            "page": cls._parse_page(doc),
            "fonts": cls._parse_fonts(doc),
            "paragraph": cls._parse_paragraph(doc),
            "headings": cls._parse_headings(doc),
            "supports_toc": True,
            "supports_abstract": True
        }
        
        return config
    
    @classmethod
    def _parse_page(cls, doc: Document) -> Dict[str, Any]:
        """解析页面设置"""
        section = doc.sections[0]
        return {
            "width": round(section.page_width.cm, 2),
            "height": round(section.page_height.cm, 2),
            "margin_top": round(section.top_margin.cm, 2),
            "margin_bottom": round(section.bottom_margin.cm, 2),
            "margin_left": round(section.left_margin.cm, 2),
            "margin_right": round(section.right_margin.cm, 2)
        }
    
    @classmethod
    def _parse_fonts(cls, doc: Document) -> Dict[str, Any]:
        """解析默认字体"""
        style = doc.styles['Normal']
        font = style.font
        
        # 获取中文字体
        east_asia = style.element.rPr.rFonts.get(qn('w:eastAsia')) if style.element.rPr.rFonts is not None else None
        
        return {
            "chinese": east_asia or "宋体",
            "english": font.name or "Times New Roman",
            "size": int(font.size.pt) if font.size else 12,
            "heading_font": "黑体",
            "heading_english": "Arial"
        }
    
    @classmethod
    def _parse_paragraph(cls, doc: Document) -> Dict[str, Any]:
        """解析段落样式"""
        style = doc.styles['Normal']
        pf = style.paragraph_format
        
        # 行距转换
        line_spacing = 1.5
        if pf.line_spacing is not None:
            if isinstance(pf.line_spacing, float):
                line_spacing = pf.line_spacing
        
        # 首行缩进
        first_indent = 0.74
        if pf.first_line_indent is not None:
            first_indent = round(pf.first_line_indent.cm, 2)
        
        alignment_map = {
            WD_ALIGN_PARAGRAPH.LEFT: "left",
            WD_ALIGN_PARAGRAPH.CENTER: "center",
            WD_ALIGN_PARAGRAPH.RIGHT: "right",
            WD_ALIGN_PARAGRAPH.JUSTIFY: "justify"
        }
        
        return {
            "line_spacing": line_spacing,
            "first_line_indent": first_indent,
            "space_before": round(pf.space_before.pt, 1) if pf.space_before else 0,
            "space_after": round(pf.space_after.pt, 1) if pf.space_after else 0,
            "alignment": alignment_map.get(pf.alignment, "justify")
        }
    
    @classmethod
    def _parse_headings(cls, doc: Document) -> Dict[str, Any]:
        """解析标题样式"""
        headings = {}
        alignment_map = {
            WD_ALIGN_PARAGRAPH.LEFT: "left",
            WD_ALIGN_PARAGRAPH.CENTER: "center",
            WD_ALIGN_PARAGRAPH.RIGHT: "right",
            WD_ALIGN_PARAGRAPH.JUSTIFY: "justify"
        }
        
        for level in range(1, 4):
            style_name = f'Heading {level}'
            try:
                style = doc.styles[style_name]
                font = style.font
                pf = style.paragraph_format
                
                east_asia = style.element.rPr.rFonts.get(qn('w:eastAsia')) if style.element.rPr.rFonts is not None else None
                
                headings[str(level)] = {
                    "level": level,
                    "font": east_asia or "黑体",
                    "font_en": font.name or "Arial",
                    "size": int(font.size.pt) if font.size else (16 - (level - 1) * 2),
                    "bold": font.bold if font.bold is not None else True,
                    "alignment": alignment_map.get(pf.alignment, "left"),
                    "space_before": round(pf.space_before.pt, 1) if pf.space_before else 12,
                    "space_after": round(pf.space_after.pt, 1) if pf.space_after else 6
                }
            except KeyError:
                # 如果文档没有该标题样式，使用默认值
                headings[str(level)] = {
                    "level": level,
                    "font": "黑体",
                    "font_en": "Arial",
                    "size": 16 - (level - 1) * 2,
                    "bold": True,
                    "alignment": "left" if level > 1 else "center",
                    "space_before": 12,
                    "space_after": 6
                }
        
        return headings
    
    @classmethod
    def get_default_template(cls) -> Dict[str, Any]:
        """获取主流默认模板"""
        return {
            "id": "default",
            "name": "默认模板",
            "description": "主流中文论文格式（A4、宋体小四、1.5倍行距）",
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
        }
