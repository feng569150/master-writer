"""
文档引擎
将论文内容转换为格式化的 Word 文档
"""

import re
import io
from typing import List, Optional, Dict
import docx
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from backend.app.models.schema import TemplateConfig, SectionResponse
from backend.app.services.template_engine import TemplateEngine


class DocumentEngine:
    """文档生成引擎"""

    @staticmethod
    def create_document(
        sections: List[SectionResponse],
        template_id: str,
        title: str = "",
        abstract: Optional[Dict] = None,
        keywords: str = "",
    ) -> Document:
        """生成 Word 文档"""
        template = TemplateEngine.get(template_id)
        if not template:
            template = TemplateConfig(id="default", name="默认")

        doc = Document()

        # ===== 页面设置 =====
        section = doc.sections[0]
        section.page_width = Cm(template.page.width)
        section.page_height = Cm(template.page.height)
        section.top_margin = Cm(template.page.margin_top)
        section.bottom_margin = Cm(template.page.margin_bottom)
        section.left_margin = Cm(template.page.margin_left)
        section.right_margin = Cm(template.page.margin_right)

        # ===== 默认样式 =====
        style = doc.styles["Normal"]
        font = style.font
        font.name = template.fonts.english
        font.size = Pt(template.fonts.size)
        # 设置中西文字体
        rpr = style.element.get_or_add_rPr()
        rFonts = rpr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rFonts)
        rFonts.set(qn("w:eastAsia"), template.fonts.chinese)

        pf = style.paragraph_format
        pf.line_spacing = template.paragraph.line_spacing
        pf.first_line_indent = Cm(template.paragraph.first_line_indent)
        pf.space_before = Pt(template.paragraph.space_before)
        pf.space_after = Pt(template.paragraph.space_after)

        # 配置标题样式
        DocumentEngine._setup_heading_styles(doc, template)

        # ===== 论文标题 =====
        if title:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(title)
            h1 = template.headings.get("1")
            h1_font_en = h1.font_en if h1 else template.fonts.english
            h1_font_zh = h1.font if h1 else "黑体"
            h1_size = (h1.size + 2) if h1 else 18
            run.font.name = h1_font_en
            run.font.size = Pt(h1_size)
            run.font.bold = True
            run.element.rPr.rFonts.set(qn("w:eastAsia"), h1_font_zh)
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(24)
            p.paragraph_format.first_line_indent = Cm(0)

        # ===== 摘要 =====
        if abstract is not None:
            zh = abstract.get("chinese", "") if isinstance(abstract, dict) else str(abstract)
            if zh:
                DocumentEngine._add_heading(doc, "摘  要", template, "1")
                p = doc.add_paragraph(zh)
                DocumentEngine._apply_paragraph_style(p, template)

                if isinstance(abstract, dict) and abstract.get("keywords_zh"):
                    kw = "；".join(abstract["keywords_zh"])
                    p = doc.add_paragraph(f"关键词：{kw}")
                    DocumentEngine._apply_paragraph_style(p, template)

                # 英文摘要
                if isinstance(abstract, dict) and abstract.get("english"):
                    DocumentEngine._add_heading(doc, "Abstract", template, "1")
                    p = doc.add_paragraph(abstract["english"])
                    DocumentEngine._apply_paragraph_style(p, template)
                    if abstract.get("keywords_en"):
                        kw_en = "; ".join(abstract["keywords_en"])
                        p = doc.add_paragraph(f"Key words: {kw_en}")
                        DocumentEngine._apply_paragraph_style(p, template)

                doc.add_page_break()

        # ===== 目录 =====
        if template.supports_toc:
            DocumentEngine._add_heading(doc, "目  录", template, "1")
            DocumentEngine._add_toc_field(doc)
            doc.add_page_break()

        # ===== 正文 =====
        for sec in sections:
            if sec.get("type") == "abstract":
                continue  # 摘要单独处理
            DocumentEngine._add_section(doc, sec, template)

        return doc

    @staticmethod
    def _add_heading(doc: Document, text: str, template: TemplateConfig, level: str):
        """添加带样式的标题"""
        p = doc.add_paragraph()
        run = p.add_run(text)
        cfg = template.headings.get(level)
        run.font.name = cfg.font_en if cfg else "Arial"
        run.font.size = Pt(cfg.size if cfg else 14)
        run.font.bold = cfg.bold if cfg else True
        run.element.rPr.rFonts.set(qn("w:eastAsia"), cfg.font if cfg else "黑体")
        pf = p.paragraph_format
        pf.space_before = Pt(cfg.space_before if cfg else 12)
        pf.space_after = Pt(cfg.space_after if cfg else 6)
        pf.first_line_indent = Cm(0)
        if cfg and cfg.alignment == "center":
            pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        # 设置大纲级别，确保目录能识别
        pPr = p._p.get_or_add_pPr()
        outlineLvl = docx.oxml.OxmlElement("w:outlineLvl")
        outlineLvl.set(qn("w:val"), str(int(level) - 1))
        pPr.append(outlineLvl)

    @staticmethod
    def _add_toc_field(doc: Document):
        """插入目录域（打开 Word 后按 F9 或右键更新域）"""
        paragraph = doc.add_paragraph()
        run = paragraph.add_run()
        fldChar = docx.oxml.OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "begin")
        run._r.append(fldChar)

        run = paragraph.add_run()
        instrText = docx.oxml.OxmlElement("w:instrText")
        instrText.set(qn("xml:space"), "preserve")
        instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
        run._r.append(instrText)

        run = paragraph.add_run()
        fldChar = docx.oxml.OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "separate")
        run._r.append(fldChar)

        run = paragraph.add_run("[打开文档后，右键此处 → 更新域，生成目录]")
        run.font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)

        run = paragraph.add_run()
        fldChar = docx.oxml.OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "end")
        run._r.append(fldChar)

    @staticmethod
    def _setup_heading_styles(doc: Document, template: TemplateConfig):
        """配置 Word 标题样式（确保导航窗格与目录可用）"""
        for level_str, cfg in template.headings.items():
            level = int(level_str)
            style_name = f"Heading {level}"
            try:
                style = doc.styles[style_name]
            except KeyError:
                style = doc.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)

            font = style.font
            font.name = cfg.font_en
            font.size = Pt(cfg.size)
            font.bold = cfg.bold
            if style.element.rPr is None:
                style.element.get_or_add_rPr()
            style.element.rPr.rFonts.set(qn("w:eastAsia"), cfg.font)

            pfp = style.paragraph_format
            pfp.space_before = Pt(cfg.space_before)
            pfp.space_after = Pt(cfg.space_after)
            if cfg.alignment == "center":
                pfp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif cfg.alignment == "right":
                pfp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            else:
                pfp.alignment = WD_ALIGN_PARAGRAPH.LEFT

    @staticmethod
    def _apply_heading_style(paragraph, template: TemplateConfig, level_str: str):
        """应用标题样式到段落"""
        cfg = template.headings.get(level_str)
        if not cfg:
            return
        for run in paragraph.runs:
            run.font.name = cfg.font_en
            run.element.rPr.rFonts.set(qn("w:eastAsia"), cfg.font)
            run.font.size = Pt(cfg.size)
            run.font.bold = cfg.bold

    @staticmethod
    def _apply_paragraph_style(paragraph, template: TemplateConfig):
        """应用正文样式"""
        for run in paragraph.runs:
            run.font.name = template.fonts.english
            run.element.rPr.rFonts.set(qn("w:eastAsia"), template.fonts.chinese)
            run.font.size = Pt(template.fonts.size)

        pf = paragraph.paragraph_format
        pf.line_spacing = template.paragraph.line_spacing
        pf.first_line_indent = Cm(template.paragraph.first_line_indent)
        pf.space_before = Pt(template.paragraph.space_before)
        pf.space_after = Pt(template.paragraph.space_after)

    @staticmethod
    def _add_section(doc: Document, section, template: TemplateConfig):
        """添加章节内容（兼容 dict 与 Pydantic 对象）"""

        def _get(key, default=""):
            if isinstance(section, dict):
                return section.get(key, default)
            return getattr(section, key, default)

        content = _get("content") or ""
        lines = content.split("\n")

        # 章节标题（如果用 style 写标题内容）
        sec_title = (_get("title") or "").strip()
        if sec_title and not any(l.strip().startswith("#") for l in lines[:3]):
            DocumentEngine._add_heading(doc, sec_title, template, "1")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Markdown 标题检测
            h_match = re.match(r"^(#{1,3})\s+(.+)$", line)
            if h_match:
                level = len(h_match.group(1))
                title_text = re.sub(r"\*\*|\*|#", "", h_match.group(2)).strip()
                DocumentEngine._add_heading(doc, title_text, template, str(level))
                continue

            # 参考文献列表（简单处理）
            if line.startswith("[") and "]" in line[:20]:
                p = doc.add_paragraph(line)
                DocumentEngine._apply_paragraph_style(p, template)
                p.paragraph_format.first_line_indent = Cm(0)
                continue

            # 普通段落
            p = doc.add_paragraph(line)
            DocumentEngine._apply_paragraph_style(p, template)

    @staticmethod
    def to_bytes(doc: Document) -> bytes:
        """将文档转为 bytes"""
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()