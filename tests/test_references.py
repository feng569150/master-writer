"""
参考文献生成与导出测试 + 自定义 Pipeline 存储测试
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

import asyncio
import io
import json
from docx import Document
from backend.app.database import db
from backend.app.services.template_engine import TemplateEngine
from backend.app.services.document_engine import DocumentEngine
from backend.app.services.model_provider import ModelManager
from backend.app.services.skill_engine import SkillEngine
from backend.app.agent.agent import WritingAgent
from backend.app.agent import pipelines as ppl


class ReferencesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await TemplateEngine.initialize()
            await ModelManager.initialize()
            SkillEngine.load_skills()
            ModelManager._default_provider = "mock"
            cls.paper_id = "reftest2"
            await db.create_paper(cls.paper_id, "参考文献测试论文", "default", None)

        asyncio.run(_init())

    def test_references_skill_saves_section(self):
        """参考文献 Skill 应生成列表并保存为 references 章节"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            async for _ in agent.run_skill(
                "references", {"topic": "深度学习", "count": 5},
                stream=False, save_to="references",
            ):
                pass
            sections = await db.get_sections(self.paper_id)
            return [s["type"] for s in sections]

        types = asyncio.run(_run())
        self.assertIn("references", types, "应有 references 章节")

    def test_references_export_formatted(self):
        """参考文献应在 docx 中以悬挂缩进列表导出"""
        async def _run():
            refs = json.dumps([
                {
                    "cite": "[1]",
                    "author": "张三",
                    "title": "深度学习研究综述",
                    "source": "计算机学报",
                    "year": "2020",
                    "formatted": "张三. 深度学习研究综述[J]. 计算机学报,2020,43(1):1-20.",
                },
                {
                    "cite": "[2]",
                    "author": "李四",
                    "title": "图像识别技术",
                    "source": "软件学报",
                    "year": "2021",
                    "formatted": "李四. 图像识别技术[J]. 软件学报,2021,32(2):50-70.",
                },
            ], ensure_ascii=False)
            await db.create_section("refsec2", self.paper_id, "references", "参考文献", refs, 0)
            paper = await db.get_paper(self.paper_id)
            sections = await db.get_sections(self.paper_id)
            doc = DocumentEngine.create_document(
                sections=sections, template_id="default", title=paper["title"]
            )
            data = DocumentEngine.to_bytes(doc)
            reopened = Document(io.BytesIO(data))
            return "\n".join(p.text for p in reopened.paragraphs)

        text = asyncio.run(_run())
        self.assertIn("参考文献", text)
        self.assertIn("深度学习研究综述", text)
        self.assertIn("图像识别技术", text)


class PipelineStorageTest(unittest.TestCase):
    """自定义 Pipeline 的创建/校验/执行/删除"""

    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await ModelManager.initialize()
            SkillEngine.load_skills()
            ModelManager._default_provider = "mock"
            cls.paper_id = "pipetest1"
            await db.create_paper(cls.paper_id, "管线测试", "default", None)

        asyncio.run(_init())

    def test_save_and_list_custom_pipeline(self):
        """自定义 pipeline 可保存并可列出"""
        async def _run():
            await ppl.save_custom_pipeline(
                "my_flow",
                "我的流程",
                "测试流程",
                [{"skill": "paper_outline", "save_to": "outline"}],
            )
            rows = await ppl.list_pipelines()
            ids = [r["id"] for r in rows]
            return ids

        ids = asyncio.run(_run())
        self.assertIn("full_paper", ids, "内置应在列表")
        self.assertIn("my_flow", ids, "自定义应在列表")

    def test_builtin_protected(self):
        """内置 pipeline 不可覆盖/删除"""
        async def _run():
            try:
                await ppl.save_custom_pipeline("full_paper", "覆盖", "", [])
                return "no_error"
            except ppl.PipelineError:
                pass
            try:
                await ppl.delete_custom_pipeline("full_paper")
                return "no_error"
            except ppl.PipelineError:
                return "protected"

        result = asyncio.run(_run())
        self.assertEqual(result, "protected")

    def test_validate_rejects_bad_definition(self):
        """非法 pipeline 定义应被拒绝"""
        async def _run():
            try:
                await ppl.save_custom_pipeline("bad_flow", "坏流程", "", [{"foo": 1}])
                return "no_error"
            except ppl.PipelineError:
                return "rejected"

        self.assertEqual(asyncio.run(_run()), "rejected")

    def test_run_custom_pipeline_by_id(self):
        """自定义 pipeline 按 ID 执行"""
        async def _run():
            await ppl.save_custom_pipeline(
                "quick_flow",
                "快速流程",
                "",
                [{"skill": "paper_outline", "save_to": "outline"}],
            )
            agent = WritingAgent(self.paper_id)
            await agent.load()
            count = 0
            async for chunk in agent.run_pipeline("quick_flow", {}, stream=True):
                count += len(chunk)
            paper = await db.get_paper(self.paper_id)
            return count, paper

        count, paper = asyncio.run(_run())
        self.assertGreater(count, 50)
        self.assertIsNotNone(paper.get("outline"), "自定义流程应保存大纲")

    def test_delete_custom_pipeline(self):
        """自定义 pipeline 可删除"""
        async def _run():
            await ppl.save_custom_pipeline("del_flow", "待删", "", [])
            await ppl.delete_custom_pipeline("del_flow")
            return await db.get_pipeline("del_flow")

        self.assertIsNone(asyncio.run(_run()))


if __name__ == "__main__":
    unittest.main(verbosity=2)