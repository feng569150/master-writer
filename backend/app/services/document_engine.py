"""
文档引擎
将论文内容转换为格式化的 Word 文档
"""

import json
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
            DocumentEngine._generate_toc(doc, sections, template)
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
    def _collect_headings(sections) -> List[tuple]:
        """从章节中收集所有 (level, title) 标题，用于目录"""
        headings = []
        import re as _re
        for sec in sections:
            if isinstance(sec, dict):
                sec_type = sec.get("type")
                sec_title = sec.get("title") or ""
                content = sec.get("content") or ""
            else:
                sec_type = getattr(sec, "type", "")
                sec_title = getattr(sec, "title", "") or ""
                content = getattr(sec, "content", "") or ""
            if sec_type in ("abstract", "references", None):
                continue
            # 章节标题作为一级
            if sec_title.strip():
                headings.append((1, _re.sub(r"[#*\s]+", " ", sec_title).strip()))
            # 内容中的 Markdown 标题
            for line in content.split("\n"):
                m = _re.match(r"^(#{1,6})\s+(.+)$", line.strip())
                if m:
                    level = len(m.group(1))
                    if level > 3:
                        level = 3
                    title = _re.sub(r"[*_`]+", "", m.group(2)).strip()
                    if title:
                        headings.append((level, title))
        return headings

    @staticmethod
    def _generate_toc(doc: Document, sections, template: TemplateConfig):
        """生成目录：预填标题列表 + TOC 域（Word 打开时自动更新页码）"""
        DocumentEngine._add_heading(doc, "目  录", template, "1")

        headings = DocumentEngine._collect_headings(sections)
        if headings:
            indent_map = {1: 0.0, 2: 0.74, 3: 1.48}
            for level, title in headings:
                p = doc.add_paragraph()
                run = p.add_run(title)
                run.font.name = template.fonts.english
                run.font.size = Pt(max(template.fonts.size - 1, 10))
                run.element.rPr.rFonts.set(qn("w:eastAsia"), template.fonts.chinese)
                pf = p.paragraph_format
                pf.first_line_indent = Cm(0)
                pf.left_indent = Cm(indent_map.get(level, 1.48))
                pf.space_before = Pt(0)
                pf.space_after = Pt(2)
                pf.line_spacing = 1.3
                # 设置大纲级别方便 Word 识别
                pPr = p._p.get_or_add_pPr()
                outlineLvl = docx.oxml.OxmlElement("w:outlineLvl")
                outlineLvl.set(qn("w:val"), str(level - 1))
                pPr.append(outlineLvl)

        # TOC 域：Word 打开后自动更新为带页码的目录
        DocumentEngine._add_toc_field(doc)
        DocumentEngine._enable_update_fields(doc)

    @staticmethod
    def _enable_update_fields(doc: Document):
        """设置 Word 打开文档时自动更新域（目录页码）"""
        try:
            settings_el = doc.settings.element
            if settings_el.find(qn("w:updateFields")) is None:
                update_fields = docx.oxml.OxmlElement("w:updateFields")
                update_fields.set(qn("w:val"), "true")
                settings_el.append(update_fields)
        except Exception:
            pass

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

        # 参考文献章节：解析 JSON 并格式化导出
        if _get("type") == "references":
            DocumentEngine._add_references(doc, content, template)
            return

        # 章节标题（如果用 style 写标题内容）
        sec_title = (_get("title") or "").strip()
        if sec_title and not any(l.strip().startswith("#") for l in lines[:3]):
            DocumentEngine._add_heading(doc, sec_title, template, "1")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Markdown 标题检测（支持 1-6 级，超过 3 级折叠为 3 级样式）
            h_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if h_match:
                level = len(h_match.group(1))
                if level > 3:
                    level = 3
                title_text = re.sub(r"\*\*|\*|#|`", "", h_match.group(2)).strip()
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
    def _add_references(doc: Document, content: str, template: TemplateConfig):
        """添加参考文献列表（悬挂缩进）"""
        # 解析 JSON 数组
        refs = []
        try:
            data = json.loads(content)
            if isinstance(data, list):
                refs = data
            elif isinstance(data, dict) and isinstance(data.get("references"), list):
                refs = data["references"]
        except (json.JSONDecodeError, TypeError):
            # 非 JSON，按行处理
            for line in content.split("\n"):
                line = line.strip()
                if line:
                    refs.append({"formatted": line})

        if not refs:
            return

        # 参考文献标题
        DocumentEngine._add_heading(doc, "参考文献", template, "1")

        for i, ref in enumerate(refs, start=1):
            formatted = ""
            cite = f"[{i}]"
            if isinstance(ref, dict):
                formatted = ref.get("formatted", "") or ""
                if ref.get("cite"):
                    cite = str(ref["cite"])
                if not formatted:
                    parts = [
                        ref.get("author", ""),
                        ref.get("title", ""),
                        ref.get("source", ""),
                        ref.get("year", ""),
                    ]
                    formatted = " ".join(p for p in parts if p)
            else:
                formatted = str(ref)

            formatted = DocumentEngine.normalize_reference(formatted)
            if not formatted:
                continue

            p = doc.add_paragraph()
            run = p.add_run(f"{cite} {formatted}" if not formatted.startswith("[") else formatted)
            DocumentEngine._apply_paragraph_style(p, template)
            # 悬挂缩进：首行缩进 0，左缩进 0.74cm
            pf = p.paragraph_format
            pf.first_line_indent = Cm(0)
            pf.left_indent = Cm(0.74)
            pf.line_spacing = 1.25

    @staticmethod
    def normalize_reference(text: str) -> str:
        """参考文献条目规范化清洗（GB/T 7714 风格）"""
        if not text:
            return ""
        # 1. 基础清洁
        t = text.strip()
        t = t.replace("\u3000", " ")  # 全角空格
        t = re.sub(r"[ \t]+", " ", t)  # 合并连续空白
        # 2. 去掉行首编号（如 [1]、1.、1、）
        t = re.sub(r"^\s*(\[\d+\]|\d+[.、]|\d+)\s*", "", t)
        # 3. 文献类型识别，确保带 [X] 标注（退化：默认 [J]，按引文编号动态判定）
        if not re.search(r"\[[A-Z]", t):
            t += " [J]"
        # 4. 结尾标点规范：去除尾部杂散标点，保留一个英文句点
        t = re.sub(r"[。．；;，,]+$", "", t).rstrip()
        if not t.endswith("."):
            t += "."
        # 5. 年份与页码间的空格清理（", 2020, 43(1): 1-20." 规范）
        t = re.sub(r",(\d{2,4})", r", \1", t)  # 数字前逗号补空格
        t = re.sub(r"\s*:\s*", ": ", t)
        return t

    @staticmethod
    def to_bytes(doc: Document) -> bytes:
        """将文档转为 bytes"""
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()