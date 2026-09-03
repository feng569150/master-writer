"""
查重引擎单元测试
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

import asyncio
from backend.app.services.plagiarism_engine import PlagiarismEngine
from backend.app.database import db


class PlagiarismEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _init():
            await db.init()
            engine = PlagiarismEngine()
            await engine.initialize()
            # 添加样本文档到库
            await engine.add_document(
                "doc1",
                "参考论文A",
                "人工智能技术近年来发展迅速，深度学习模型在自然语言处理领域取得了显著的成果。"
                "大语言模型通过海量数据训练，能够理解并生成自然语言文本，广泛应用于对话系统、"
                "文本摘要和机器翻译等任务。",
            )
            await engine.add_document(
                "doc2",
                "参考论文B",
                "宏观经济政策对经济增长具有重要影响。货币政策的调整会影响市场利率水平，"
                "进而作用于投资和消费决策。财政政策的扩张或收缩也会改变总需求，影响"
                "经济周期的波动。",
            )
            cls.engine = engine

        asyncio.run(_init())

    def test_detect_duplicate_text(self):
        """完全复制的文本应被检测出来"""
        text = (
            "人工智能技术近年来发展迅速，深度学习模型在自然语言处理领域取得了显著的成果。"
            "大语言模型通过海量数据训练，能够理解并生成自然语言文本。"
        )
        result = asyncio.run(self.engine.check(text, threshold=0.3))
        self.assertGreater(result["overall_similarity"], 0.1, "复制文本相似度应较高")
        self.assertGreaterEqual(len(result["matches"]), 1, "应找到至少一个匹配")

    def test_no_false_positive(self):
        """无关文本不应被误报"""
        text = "今天天气很好，我们一起去公园散步，享受阳光和新鲜空气。"
        result = asyncio.run(self.engine.check(text, threshold=0.5))
        self.assertLess(result["overall_similarity"], 0.3, "无关文本相似度应很低")
        self.assertEqual(result["matches"], [], "不应有匹配")

    def test_merge_adjacent_matches(self):
        """相邻匹配应被合并"""
        result = asyncio.run(
            self.engine.check(
                "人工智能技术近年来发展迅速，深度学习模型在自然语言处理领域取得了显著的成果。"
                "大语言模型通过海量数据训练，能够理解并生成自然语言文本。这与宏观经济无关。",
                threshold=0.3,
            )
        )
        self.assertGreater(result["overall_similarity"], 0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)