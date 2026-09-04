"""
模型提供者单元测试
流式 chunk 容错解析 + API Key 脱敏
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests._base  # noqa: F401

from backend.app.services.model_provider import OpenAICompatibleProvider
from backend.app.services import model_provider as mp


class StreamChunkParseTest(unittest.TestCase):
    """各种供应商的非标准流式 chunk 都应被安全解析"""

    def setUp(self):
        self.parse = OpenAICompatibleProvider._parse_stream_chunk

    def test_normal_chunk(self):
        chunk = {"choices": [{"delta": {"content": "你好"}}]}
        self.assertEqual(self.parse(chunk), "你好")

    def test_empty_choices(self):
        """choices 为空数组（用量统计块）不应崩溃"""
        chunk = {"choices": [], "usage": {"total_tokens": 100}}
        self.assertEqual(self.parse(chunk), "")

    def test_missing_choices(self):
        chunk = {"id": "chatcmpl-x"}
        self.assertEqual(self.parse(chunk), "")

    def test_error_chunk(self):
        chunk = {"error": {"message": "rate limit exceeded"}}
        self.assertEqual(self.parse(chunk), "")

    def test_delta_without_content(self):
        chunk = {"choices": [{"delta": {"role": "assistant"}}]}
        self.assertEqual(self.parse(chunk), "")

    def test_role_only_then_content(self):
        c1 = {"choices": [{"delta": {"role": "assistant"}}]}
        c2 = {"choices": [{"delta": {"content": "回答内容"}}]}
        self.assertEqual(self.parse(c1) + self.parse(c2), "回答内容")


class ApiKeyMaskTest(unittest.TestCase):
    """API Key 脱敏显示与提交保留逻辑"""

    def test_mask_long_key(self):
        key = "sk-abcdef1234567890wxyz"
        masked = mp.ModelManager.mask_api_key(key)
        self.assertNotIn("abcdef1234567890wxyz", masked, "中间部分应掩码")
        self.assertIn("*", masked)
        self.assertTrue(masked.startswith("sk-"))

    def test_mask_short_key(self):
        masked = mp.ModelManager.mask_api_key("123456")
        self.assertNotIn("456", masked, "短 key 应全掩")

    def test_mask_empty(self):
        self.assertEqual(mp.ModelManager.mask_api_key(""), "")

    def test_is_masked(self):
        self.assertTrue(mp.ModelManager.is_masked("sk-****"))
        self.assertFalse(mp.ModelManager.is_masked("sk-abcdef"))

    def test_save_keeps_original_when_masked(self):
        """传入掩码值时不应覆盖原 Key"""
        import asyncio

        async def _run():
            await mp.ModelManager.save_config(
                "masktest", "sk-REAL-KEY-123456", "m1", "", set_default=False
            )
            await mp.ModelManager.save_config(
                "masktest", "sk-****REAL", "m1", "", set_default=False
            )
            return mp.ModelManager.get_config("masktest").api_key

        self.assertEqual(asyncio.run(_run()), "sk-REAL-KEY-123456")


if __name__ == "__main__":
    unittest.main(verbosity=2)