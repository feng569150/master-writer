"""
模型提供者流式解析容错测试
覆盖各种供应商的非标准流式 chunk 格式
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

from backend.app.services.model_provider import OpenAICompatibleProvider


class StreamChunkParseTest(unittest.TestCase):
    def setUp(self):
        self.parse = OpenAICompatibleProvider._parse_stream_chunk

    def test_normal_chunk(self):
        """标准 OpenAI 格式 chunk 返回内容"""
        chunk = {"choices": [{"delta": {"content": "你好"}}]}
        self.assertEqual(self.parse(chunk), "你好")

    def test_empty_choices(self):
        """choices 为空数组的 chunk（用量统计块）不应崩溃，返回空串"""
        chunk = {"choices": [], "usage": {"total_tokens": 100}}
        self.assertEqual(self.parse(chunk), "")

    def test_missing_choices(self):
        """无 choices 字段的 chunk（如错误/异常事件）返回空串"""
        chunk = {"id": "chatcmpl-x", "object": "chat.completion.chunk"}
        self.assertEqual(self.parse(chunk), "")

    def test_error_chunk(self):
        """error 块返回空串"""
        chunk = {"error": {"message": "rate limit exceeded"}}
        self.assertEqual(self.parse(chunk), "")

    def test_delta_without_content(self):
        """delta 仅有 role 的 chunk（流开始处）返回空串"""
        chunk = {"choices": [{"delta": {"role": "assistant"}}]}
        self.assertEqual(self.parse(chunk), "")

    def test_role_only_choice_then_content(self):
        """多个 chunk 流：role 块 + 内容块"""
        c1 = {"choices": [{"delta": {"role": "assistant"}}]}
        c2 = {"choices": [{"delta": {"content": "回答内容"}}]}
        self.assertEqual(self.parse(c1) + self.parse(c2), "回答内容")


if __name__ == "__main__":
    unittest.main(verbosity=2)