"""
模板引擎单元测试
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401  (设置临时数据目录)

import asyncio
from backend.app.services.template_engine import TemplateEngine
from backend.app.services.template_parser import TemplateParser
from backend.app.database import db


class TemplateEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await TemplateEngine.initialize()

        asyncio.run(_init())

    def test_default_template_always_exists(self):
        """默认模板必须存在"""
        template = TemplateEngine.get("default")
        self.assertIsNotNone(template, "缺少默认模板")
        self.assertEqual(template.name, "默认模板")

    def test_builtin_templates_loaded(self):
        """内置模板应加载"""
        self.assertIsNotNone(TemplateEngine.get("bachelor_thesis"))
        self.assertIsNotNone(TemplateEngine.get("course_paper"))

    def test_default_template_uses_mainstream_format(self):
        """默认模板应符合主流中文论文格式"""
        t = TemplateEngine.get("default")
        self.assertEqual(t.page.width, 21.0, "A4 宽度")
        self.assertEqual(t.page.height, 29.7, "A4 高度")
        self.assertEqual(t.fonts.chinese, "宋体", "正文中文字体应为宋体")
        self.assertEqual(t.fonts.size, 12, "小四号=12pt")
        self.assertEqual(t.paragraph.line_spacing, 1.5, "1.5倍行距")
        self.assertAlmostEqual(t.paragraph.first_line_indent, 0.74, places=1, msg="首行缩进2字符≈0.74cm")
        self.assertEqual(t.headings["1"].font, "黑体")

    def test_parser_reads_docx(self):
        """解析器应能从 docx 中提取配置"""
        config = TemplateParser.get_default_template()
        self.assertEqual(config["fonts"]["chinese"], "宋体")
        self.assertIn("1", config["headings"])

    def test_list_all_returns_templates(self):
        """列表接口返回模板响应"""
        result = TemplateEngine.list_all()
        self.assertGreaterEqual(len(result), 3)

    def test_delete_custom_template(self):
        """自定义模板可删除"""
        async def _run():
            await TemplateEngine.create_custom(
                "test_custom_tpl", "测试模板", TemplateParser.get_default_template()
            )
            self.assertIsNotNone(TemplateEngine.get("test_custom_tpl"))
            await TemplateEngine.delete_custom("test_custom_tpl")
            return TemplateEngine.get("test_custom_tpl")

        result = asyncio.run(_run())
        self.assertIsNone(result, "删除后不应再存在")

    def test_cannot_delete_builtin(self):
        """内置模板不可删除"""
        async def _run():
            try:
                await TemplateEngine.delete_custom("default")
                return False
            except ValueError:
                return True

        self.assertTrue(asyncio.run(_run()), "内置模板删除应抛异常")
        self.assertIsNotNone(TemplateEngine.get("default"), "内置模板应保留")

    def test_update_custom_template(self):
        """自定义模板可编辑更新"""
        async def _run():
            cfg = TemplateParser.get_default_template()
            cfg["id"] = "edit_tpl_test"
            await TemplateEngine.create_custom("edit_tpl_test", "原名", cfg)
            # 修改名称字号
            cfg2 = dict(cfg)
            cfg2["fonts"] = {**cfg["fonts"], "size": 14}
            updated = await TemplateEngine.update_custom("edit_tpl_test", "新名", cfg2)
            return updated

        t = asyncio.run(_run())
        self.assertEqual(t.name, "新名")
        self.assertEqual(t.fonts.size, 14, "字号应更新")

    def test_cannot_update_builtin(self):
        """内置模板不可编辑"""
        async def _run():
            try:
                await TemplateEngine.update_custom("default", "改名", {})
                return False
            except ValueError:
                return True

        self.assertTrue(asyncio.run(_run()), "内置模板编辑应抛异常")
        self.assertEqual(TemplateEngine.get("default").name, "默认模板", "内置模板名不应变化")

    def test_manual_create_partial_config(self):
        """手动定义模板：仅填部分字段也应有完整默认配置"""
        async def _run():
            base = TemplateParser.get_default_template()
            partial = dict(base)
            partial.update({
                "fonts": {"chinese": "仿宋", "size": 10.5},
                "paragraph": {"line_spacing": 1.25},
            })
            t = await TemplateEngine.create_custom("manual_tpl", "手动模板", partial)
            return t

        t = asyncio.run(_run())
        self.assertEqual(t.fonts.chinese, "仿宋")
        self.assertEqual(t.fonts.size, 10.5)
        self.assertEqual(t.paragraph.line_spacing, 1.25)
        # 默认字段应保留
        self.assertEqual(t.fonts.english, "Times New Roman")
        self.assertEqual(t.page.margin_top, 2.54)
        self.assertIn("1", t.headings)


if __name__ == "__main__":
    unittest.main(verbosity=2)