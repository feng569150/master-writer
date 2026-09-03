"""
Agent 编排单元测试
使用 MockProvider 验证完整写作流程（无需 API Key）
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

import asyncio
import json
from backend.app.database import db
from backend.app.services.model_provider import ModelManager
from backend.app.services.skill_engine import SkillEngine
from backend.app.agent.memory import MemoryStore
from backend.app.agent.agent import WritingAgent


class AgentPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            await ModelManager.initialize()
            SkillEngine.load_skills()
            # 强制使用 mock
            ModelManager._default_provider = "mock"
            cls.paper_id = "testpaper1"
            await db.create_paper(
                cls.paper_id,
                "基于深度学习的文本分类研究",
                "default",
                None,
            )

        asyncio.run(_init())

    def _collect(self, agen):
        """收集异步生成器的所有输出"""
        async def _run():
            chunks = []
            async for c in agen:
                chunks.append(c)
            return "".join(chunks)

        return asyncio.run(_run())

    def test_skills_loaded(self):
        """Skill 应全部加载"""
        skills = SkillEngine.list_skills()
        ids = {s["id"] for s in skills}
        self.assertIn("paper_outline", ids)
        self.assertIn("introduction", ids)
        self.assertIn("body_writing", ids)
        self.assertIn("conclusion", ids)
        self.assertIn("abstract", ids)

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
        self.assertGreater(len(result), 100, "Mock 输出不应为空")

    def test_outline_skill_saves_to_memory(self):
        """大纲 Skill 应生成 JSON 并保存到记忆"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            out = ""
            async for chunk in agent.run_skill("paper_outline", {"topic": "测试题目"}, stream=False):
                out += chunk
            await MemoryStore.save(self.paper_id)
            memory = MemoryStore.get(self.paper_id)
            return out, memory

        out, memory = asyncio.run(_run())
        # 输出应为 JSON（直接从 executor 返回值）
        self.assertIsNotNone(memory.outline, "大纲应保存到记忆")
        if isinstance(memory.outline, dict):
            self.assertIn("sections", memory.outline)

    def test_full_pipeline_streams_chunks(self):
        """完整 Pipeline 应流式产出过程中的分块"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            count = 0
            async for chunk in agent.run_pipeline("outline_only", {}, stream=True):
                count += len(chunk)
            return count

        count = asyncio.run(_run())
        self.assertGreater(count, 50, "Pipeline 应产生输出")

    def test_reflect_returns_feedback(self):
        """反思应返回审稿意见"""
        async def _run():
            agent = WritingAgent(self.paper_id)
            await agent.load()
            result = await agent.reflect("本文研究了一种新的方法，实验效果很好。")
            return result

        result = asyncio.run(_run())
        self.assertGreater(len(result), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)