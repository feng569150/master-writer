"""
PDF 转换器单元测试（不依赖真实 Word/LibreOffice 的路径逻辑）
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

from backend.app.services import pdf_converter


class PdfConverterTest(unittest.TestCase):
    def test_find_soffice_none(self):
        """无 LibreOffice 时应返回 None（不报错）"""
        with mock.patch.object(pdf_converter.shutil, "which", return_value=None), \
             mock.patch.object(pdf_converter.os.path, "exists", return_value=False):
            self.assertIsNone(pdf_converter._find_soffice())

    def test_find_soffice_which(self):
        """PATH 中存在 soffice 时应找到"""
        with mock.patch.object(pdf_converter.shutil, "which", return_value="/usr/bin/soffice"), \
             mock.patch.object(pdf_converter.os.path, "exists", return_value=True):
            self.assertEqual(pdf_converter._find_soffice(), "/usr/bin/soffice")

    def test_convert_no_tool_raises_hint(self):
        """无任何转换器时应抛出带安装指引的错误"""
        with mock.patch.object(pdf_converter, "_convert_with_com", return_value=False), \
             mock.patch.object(pdf_converter, "_convert_with_soffice", return_value=False), \
             mock.patch.object(pdf_converter.os, "name", "posix"):
            with self.assertRaises(pdf_converter.PdfConversionError) as ctx:
                pdf_converter.convert_docx_to_pdf("/tmp/a.docx", "/tmp/a.pdf")
            self.assertIn("LibreOffice", str(ctx.exception))

    @mock.patch.object(pdf_converter, "_convert_with_com", return_value=True)
    def test_com_used_first(self, _com):
        """优先尝试 COM 转换"""
        with mock.patch.object(pdf_converter, "_convert_with_soffice") as soffice:
            pdf_converter.convert_docx_to_pdf("a.docx", "a.pdf")
            soffice.assert_not_called()

    @mock.patch.object(pdf_converter, "_convert_with_soffice", return_value=True)
    def test_soffice_fallback(self, _soffice):
        """COM 失败时回退 LibreOffice"""
        with mock.patch.object(pdf_converter, "_convert_with_com", return_value=False):
            pdf_converter.convert_docx_to_pdf("a.docx", "a.pdf")
            _soffice.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)