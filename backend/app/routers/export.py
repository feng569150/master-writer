"""
导出路由
"""

import os
import asyncio
import json
import uuid
from urllib.parse import quote
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from backend.app.models.schema import ResponseBase, ExportRequest
from backend.app.services.document_engine import DocumentEngine
from backend.app.services.pdf_converter import convert_docx_to_pdf, PdfConversionError, detect_converter
from backend.app.config import settings
from backend.app.database import db

router = APIRouter(prefix="/api/export", tags=["导出"])


def _download_header(filename: str) -> str:
    """生成兼容中文文件名的 Content-Disposition"""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


@router.post("/docx")
async def export_docx(req: ExportRequest):
    """导出 Word 文档"""
    try:
        paper = await db.get_paper(req.paper_id)
        if not paper:
            return JSONResponse(status_code=404, content={"success": False, "message": "论文不存在"})
        
        sections = await db.get_sections(req.paper_id)
        
        # 提取摘要
        abstract = None
        body_sections = []
        for sec in sections:
            if sec.get("type") == "abstract":
                try:
                    abstract = json.loads(sec.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    abstract = {"chinese": sec.get("content", "")}
            else:
                body_sections.append(sec)
        
        # 生成文档
        doc = DocumentEngine.create_document(
            sections=body_sections,
            template_id=paper["template_id"],
            title=paper["title"],
            abstract=abstract
        )
        
        # 转为 bytes
        doc_bytes = DocumentEngine.to_bytes(doc)
        
        header = _download_header(f"{paper['title'] or 'paper'}.docx")
        print(f"[EXPORT] header={header!r} ascii={all(ord(c) < 128 for c in header)}", flush=True)
        
        return StreamingResponse(
            iter([doc_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": header
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"导出失败: {str(e)}"}
        )


@router.post("/markdown")
async def export_markdown(req: ExportRequest):
    """导出 Markdown"""
    try:
        paper = await db.get_paper(req.paper_id)
        if not paper:
            return JSONResponse(status_code=404, content={"success": False, "message": "论文不存在"})
        
        sections = await db.get_sections(req.paper_id)
        
        md_content = f"# {paper['title']}\n\n"
        for sec in sections:
            if sec.get("title"):
                md_content += f"## {sec['title']}\n\n"
            if sec.get("content"):
                md_content += f"{sec['content']}\n\n"
        
        return StreamingResponse(
            iter([md_content.encode("utf-8")]),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": _download_header(f"{paper['title'] or 'paper'}.md")
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"导出失败: {str(e)}"}
        )


@router.post("/pdf")
async def export_pdf(req: ExportRequest):
    """导出 PDF（先生成 docx，再调用本机转换器）"""
    try:
        paper = await db.get_paper(req.paper_id)
        if not paper:
            return JSONResponse(status_code=404, content={"success": False, "message": "论文不存在"})

        sections = await db.get_sections(req.paper_id)
        abstract = None
        body_sections = []
        for sec in sections:
            if sec.get("type") == "abstract":
                try:
                    abstract = json.loads(sec.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    abstract = {"chinese": sec.get("content", "")}
            else:
                body_sections.append(sec)

        doc = DocumentEngine.create_document(
            sections=body_sections,
            template_id=paper["template_id"],
            title=paper["title"],
            abstract=abstract,
        )

        # 写临时 docx，再转换 PDF（COM 为同步阻塞，放线程池避免阻塞事件循环）
        os.makedirs(settings.EXPORT_TEMP_DIR, exist_ok=True)
        token = uuid.uuid4().hex[:10]
        docx_path = os.path.join(settings.EXPORT_TEMP_DIR, f"{token}.docx")
        pdf_path = os.path.join(settings.EXPORT_TEMP_DIR, f"{token}.pdf")
        try:
            await asyncio.to_thread(doc.save, docx_path)
            await asyncio.to_thread(convert_docx_to_pdf, docx_path, pdf_path)
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
        finally:
            for p in (docx_path, pdf_path):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": _download_header(f"{paper['title'] or 'paper'}.pdf")
            }
        )
    except PdfConversionError as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"导出失败: {str(e)}"}
        )


@router.get("/pdf/check")
async def pdf_check():
    """检测本机 PDF 转换器可用性"""
    conv = detect_converter()
    return ResponseBase(data={"converter": conv})
