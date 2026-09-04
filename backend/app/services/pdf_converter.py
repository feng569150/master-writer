"""
PDF 转换器
docx → pdf，优先使用本机 Word/WPS COM（Windows），其次 LibreOffice
"""

import os
import shutil
import subprocess
from typing import Optional


class PdfConversionError(Exception):
    pass


def _find_soffice() -> Optional[str]:
    """查找 LibreOffice 可执行文件"""
    candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _has_com_module() -> bool:
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def _convert_with_com(docx_path: str, pdf_path: str) -> bool:
    """
    使用 Word / WPS COM 转换（Windows + Office/WPS）。
    返回是否成功；未安装 COM 组件时返回 False。
    """
    if not _has_com_module():
        return False
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    doc = None
    success = False
    try:
        # 优先 Word，退而求其次 WPS（KWPS.Application）
        try:
            app = win32com.client.DispatchEx("Word.Application")
        except Exception:
            try:
                app = win32com.client.DispatchEx("KWPS.Application")
            except Exception:
                return False

        app.Visible = False
        try:
            doc = app.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
            doc.ExportAsFixedFormat(
                os.path.abspath(pdf_path),
                17,  # wdExportFormatPDF
            )
            success = os.path.exists(pdf_path)
        except Exception:
            success = False
    finally:
        # 关闭尽量不抛错，Quit 失败不影响结果
        try:
            if doc:
                doc.Close(False)
        except Exception:
            pass
        try:
            if app:
                app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return success


def _convert_with_soffice(docx_path: str, pdf_path: str) -> bool:
    """使用 LibreOffice 命令行转换"""
    soffice = _find_soffice()
    if not soffice:
        return False
    out_dir = os.path.dirname(pdf_path)
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            out_dir,
            os.path.abspath(docx_path),
        ],
        capture_output=True,
        timeout=120,
    )
    # LibreOffice 输出文件名 = docx 同名 + .pdf
    expected = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    if result.returncode == 0 and os.path.exists(expected):
        if os.path.abspath(expected) != os.path.abspath(pdf_path):
            shutil.move(expected, pdf_path)
        return os.path.exists(pdf_path)
    return False


def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> None:
    """转换 docx → pdf；失败抛出 PdfConversionError（附安装指引）"""
    if _convert_with_com(docx_path, pdf_path):
        return
    if _convert_with_soffice(docx_path, pdf_path):
        return

    hint = []
    if os.name == "nt" and not _has_com_module():
        hint.append("pip install pywin32（并使用 Word 或 WPS）")
    hint.append("安装 LibreOffice（https://www.libreoffice.org/download/）")
    raise PdfConversionError(
        "未找到可用的 PDF 转换器。请任选其一："
        + "；或".join(hint)
    )


def detect_converter() -> str:
    """检测当前环境可用的转换器（用于前端提示）"""
    if _has_com_module():
        import win32com.client

        try:
            app = win32com.client.DispatchEx("Word.Application")
            app.Quit()
            return "word"
        except Exception:
            try:
                app = win32com.client.DispatchEx("KWPS.Application")
                app.Quit()
                return "wps"
            except Exception:
                pass
    if _find_soffice():
        return "libreoffice"
    return "none"