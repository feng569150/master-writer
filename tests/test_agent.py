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

    def test_target_words_persist(self):
        """目标字数应随论文创建/更新持久化"""
        async def _run():
            pid = "wordstest1"
            await db.create_paper(pid, "字数测试", "default", None, target_words=3000)
            paper = await db.get_paper(pid)
            # 更新
            await db.update_paper(pid, target_words=5000)
            paper2 = await db.get_paper(pid)
            return paper.get("target_words"), paper2.get("target_words")

        w1, w2 = asyncio.run(_run())
        self.assertEqual(w1, 3000)
        self.assertEqual(w2, 5000)

    def test_segmented_body_writing(self):
        """repeat 分段续写：章节内容应跨多段累计变长"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            agent.state["outline"] = {"sections": [{"level": 1, "title": "第一章 概述", "word_count": 3000, "children": []}]}
            custom = {
                "name": "分段测试",
                "steps": [
                    {
                        "loop": {
                            "over": "outline.sections", "as": "section",
                            "steps": [{
                                "skill": "body_writing",
                                "inputs": {"section_title": "{{section.title}}", "section_outline": "{{section}}"},
                                "save_to": "sections",
                                "repeat": "{{section.word_count}}",
                            }],
                        }
                    }
                ],
            }
            async for _ in agent.run_pipeline(custom, {}, stream=True):
                pass
            sections = await db.get_sections(self.paper_id)
            sec = next((s for s in sections if s["title"] == "第一章 概述"), None)
            return len(sec["content"]) if sec else 0

        length = asyncio.run(_run())
        # 3000 字 → ceil(3000/800)=4 段，每段 mock ~180 字，累计应明显多于单段
        self.assertGreaterEqual(length, 400, "多段续写应累计出较长内容")

    def test_citations_discovered_by_references(self):
        """references 步骤应自动统计正文引文数并注入 count（编号一致）"""
        async def _run():
            from backend.app.agent.executor import extract_citations
            sections = [
                {"type": "body", "title": "第一章", "content": "研究[1]指出，深度学习[2]应用广泛。相关方法见文献[3]。"},
                {"type": "body", "title": "第二章", "content": "背景如[1]所述。"},
            ]
            n = extract_citations(sections)
            return n

        self.assertEqual(asyncio.run(_run()), 3, "应统计出最大引文编号")

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