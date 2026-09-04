"""
Agent/Pipeline 编排单元测试
使用 MockProvider 验证完整写作流程（无需 API Key）
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

import asyncio
from backend.app.database import db
from backend.app.services.model_provider import ModelManager
from backend.app.services.skill_engine import SkillEngine
from backend.app.agent.agent import WritingAgent


class AgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await ModelManager.initialize()
            SkillEngine.load_skills()
            ModelManager._default_provider = "mock"
            cls.paper_id = "agenttest1"
            await db.create_paper(cls.paper_id, "测试论文", "default", None)

        asyncio.run(_init())

    def _collect(self, agen):
        """收集异步生成器所有输出"""
        async def _run():
            chunks = []
            async for c in agen:
                chunks.append(c)
            return "".join(chunks)

        return asyncio.run(_run())

    def test_skills_loaded(self):
        """Skill 应全部加载"""
        ids = {s["id"] for s in SkillEngine.list_skills()}
        for sid in ("paper_outline", "introduction", "body_writing", "conclusion", "abstract", "references"):
            self.assertIn(sid, ids)

    def test_mock_provider_works(self):
        """MockProvider 应可流式生成内容"""
        async def _run():
            out = ""
            async for chunk in ModelManager.generate_stream(
                [{"role": "user", "content": "请生成论文大纲"}]
            ):
                out += chunk
            return out

        result = asyncio.run(_run())
        self.assertGreater(len(result), 100)

    def test_run_skill_saves_outline(self):
        """run_skill 生成大纲应保存到论文状态与数据库"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            out = ""
            async for chunk in agent.run_skill(
                "paper_outline", {"topic": "测试"}, stream=False, save_to="outline"
            ):
                out += chunk
            assert agent.state.get("outline") is not None, "outline 未保存"
            assert isinstance(agent.state["outline"], dict)
            paper = await db.get_paper(self.paper_id)
            return paper

        paper = asyncio.run(_run())
        self.assertIsNotNone(paper.get("outline"), "outline 应写回数据库")

    def test_full_pipeline_streams_and_persists(self):
        """一键成文：大纲→正文循环→摘要→参考文献 全部生成并持久化"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            count = 0
            async for chunk in agent.run_pipeline("full_paper", {}, stream=True):
                count += len(chunk)
            sections = await db.get_sections(self.paper_id)
            paper = await db.get_paper(self.paper_id)
            return paper, sections, count

        paper, sections, count = asyncio.run(_run())
        self.assertGreater(count, 100)
        self.assertIsNotNone(paper.get("outline"), "应有大纲")
        types = [s["type"] for s in sections]
        self.assertIn("abstract", types, "应有摘要")
        self.assertIn("references", types, "应有参考文献")
        self.assertGreaterEqual(types.count("body"), 1, "应有正文")

    def test_individual_steps_persist(self):
        """单步生成（摘要+结论）都应保存，导出时不会缺章节"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            # 摘要
            async for _ in agent.run_skill(
                "abstract", {"full_text": "正文内容"}, stream=False, save_to="abstract"
            ):
                pass
            # 结论（单步，save_to=sections + section_title）
            async for _ in agent.run_skill(
                "conclusion", {"topic": "测试", "section_title": "结论"},
                stream=False, save_to="sections",
            ):
                pass
            sections = await db.get_sections(self.paper_id)
            return sections

        sections = asyncio.run(_run())
        types = [s["type"] for s in sections]
        self.assertIn("abstract", types, "摘要应落库")
        self.assertIn("conclusion", types, "结论应落库")
        conc = next(s for s in sections if s["type"] == "conclusion")
        self.assertGreater(len(conc["content"]), 10, "结论应有内容")

    def test_custom_pipeline_dict(self):
        """用户自定义 pipeline（dict 形式）应可执行"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            custom = {
                "name": "自定义流程",
                "steps": [
                    {"skill": "paper_outline", "save_to": "outline"},
                    {"skill": "conclusion", "inputs": {"topic": "{{title}}", "section_title": "结论"}, "save_to": "sections"},
                ],
            }
            count = 0
            async for chunk in agent.run_pipeline(custom, {}, stream=True):
                count += len(chunk)
            sections = await db.get_sections(self.paper_id)
            return count, sections

        count, sections = asyncio.run(_run())
        self.assertGreater(count, 50)
        types = [s["type"] for s in sections]
        self.assertIn("conclusion", types, "自定义步骤的结论应落库")


if __name__ == "__main__":
    unittest.main(verbosity=2)