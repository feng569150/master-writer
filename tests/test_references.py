"""
参考文献生成与导出测试
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
from backend.app.agent.memory import MemoryStore
from backend.app.agent.agent import WritingAgent


class ReferencesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await TemplateEngine.initialize()
            await ModelManager.initialize()
            SkillEngine.load_skills()
            ModelManager._default_provider = "mock"
            cls.paper_id = "reftest1"
            await db.create_paper(cls.paper_id, "参考文献测试论文", "default", None)

        asyncio.run(_init())

    def test_references_skill_saves_section(self):
        """参考文献 Skill 应生成列表并保存为 references 章节"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            out = ""
            async for chunk in agent.run_skill(
                "references",
                {"topic": "深度学习", "count": 5},
                stream=False,
            ):
                out += chunk
            await MemoryStore.save(self.paper_id)
            sections = await db.get_sections(self.paper_id)
            ref_types = [s["type"] for s in sections]
            return ref_types

        types = asyncio.run(_run())
        self.assertIn("references", types, "应有 references 章节")

    def test_references_export_formatted(self):
        """参考文献应在 docx 中以悬挂缩进列表导出"""
        async def _run():
            # 手动构造 references 章节（模拟 AI 输出）
            refs = json.dumps([
                {
                    "cite": "[1]",
                    "author": "张三",
                    "title": "深度学习研究综述",
                    "source": "计算机学报",
                    "year": "2020",
                    "formatted": "张三. 深度学习研究综述[J]. 计算机学报, 2020, 43(1): 1-20.",
                },
                {
                    "cite": "[2]",
                    "author": "李四",
                    "title": "图像识别技术",
                    "source": "软件学报",
                    "year": "2021",
                    "formatted": "李四. 图像识别技术[J]. 软件学报, 2021, 32(2): 50-70.",
                },
            ], ensure_ascii=False)
            await db.create_section("refsec1", self.paper_id, "references", "参考文献", refs, 0)

            paper = await db.get_paper(self.paper_id)
            sections = await db.get_sections(self.paper_id)
            doc = DocumentEngine.create_document(
                sections=sections, template_id="default", title=paper["title"]
            )
            data = DocumentEngine.to_bytes(doc)
            reopened = Document(io.BytesIO(data))
            joined = "\n".join(p.text for p in reopened.paragraphs)
            return joined

        text = asyncio.run(_run())
        self.assertIn("参考文献", text)
        self.assertIn("深度学习研究综述", text)
        self.assertIn("图像识别技术", text)


class FullPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await TemplateEngine.initialize()
            await ModelManager.initialize()
            SkillEngine.load_skills()
            ModelManager._default_provider = "mock"
            cls.paper_id = "pipefull1"
            await db.create_paper(cls.paper_id, "一键成文测试", "default", None)

        asyncio.run(_init())

    def test_full_paper_pipeline(self):
        """一键成文：大纲→正文→摘要→参考文献应全部生成"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            count = 0
            async for chunk in agent.run_pipeline("full_paper", {}, stream=True):
                count += len(chunk)
            await MemoryStore.save(self.paper_id)
            paper = await db.get_paper(self.paper_id)
            sections = await db.get_sections(self.paper_id)
            return paper, sections, count

        paper, sections, count = asyncio.run(_run())
        self.assertGreater(count, 100, "Pipeline 应有实质输出")
        self.assertIsNotNone(paper["outline"], "大纲应生成")
        types = [s["type"] for s in sections]
        self.assertIn("abstract", types, "摘要应生成")
        self.assertIn("references", types, "参考文献应生成")
        body_count = len([t for t in types if t == "body"])
        self.assertGreaterEqual(body_count, 1, "应有正文章节")


if __name__ == "__main__":
    unittest.main(verbosity=2)