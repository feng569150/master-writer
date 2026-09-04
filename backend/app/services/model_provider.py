"""
模型提供者抽象层
统一封装各种 AI 模型的调用接口，支持本地 Mock 模式
"""

import json
import httpx
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any, Optional
from backend.app.config import settings
from backend.app.models.schema import ChatMessage, ModelConfig
from backend.app.database import db


class ModelProvider(ABC):
    """模型提供者抽象基类"""

    name: str = "base"

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], **params) -> AsyncGenerator[str, None]:
        """流式对话生成"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置是否可用"""
        pass

    async def close(self):
        pass


class OpenAICompatibleProvider(ModelProvider):
    """OpenAI 兼容接口（OpenAI、智谱、DeepSeek 等）"""

    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=120.0)

    def validate_config(self) -> bool:
        return bool(self.api_key and self.model)

    async def chat(self, messages: List[Dict[str, str]], **params) -> AsyncGenerator[str, None]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **{k: v for k, v in params.items() if v is not None},
        }

        async with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or line.strip() == "":
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = type(self)._parse_stream_chunk(chunk)
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    @staticmethod
    def _parse_stream_chunk(chunk: dict) -> str:
        """从流式 chunk 提取文本内容，容错各种非标准格式"""
        # 错误块
        if chunk.get("error"):
            return ""
        # 缺失或空 choices（如用法统计块）
        choices = chunk.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""

    async def close(self):
        await self.client.aclose()


class OllamaProvider(ModelProvider):
    """本地 Ollama 模型"""

    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)

    def validate_config(self) -> bool:
        return bool(self.model)

    async def chat(self, messages: List[Dict[str, str]], **params) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **{k: v for k, v in params.items() if v is not None},
        }

        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    async def close(self):
        await self.client.aclose()


class MockProvider(ModelProvider):
    """
    本地模拟提供者
    无 API Key 时可用：根据 prompt 生成结构化的示例内容，
    用于跑通完整流程和演示
    """

    name = "mock"

    def __init__(self):
        self.model = "mock-local"

    def validate_config(self) -> bool:
        return True  # 永远可用

    async def chat(self, messages: List[Dict[str, str]], **params) -> AsyncGenerator[str, None]:
        prompt = messages[-1]["content"] if messages else ""
        text = MockProvider._generate(prompt)
        # 模拟流式输出，每 40 个字符一段
        for i in range(0, len(text), 40):
            yield text[i : i + 40]

    @staticmethod
    def _generate(prompt: str) -> str:
        """根据 prompt 生成模拟内容"""
        # 检测任务类型（提供实用内容，而非乱码）
        if "大纲" in prompt or "outline" in prompt.lower():
            return MockProvider._mock_outline()
        if "摘要" in prompt or "abstract" in prompt.lower():
            return MockProvider._mock_abstract()
        if "引言" in prompt or "introduction" in prompt.lower():
            return MockProvider._mock_introduction()
        if "结论" in prompt or "conclusion" in prompt.lower():
            return MockProvider._mock_conclusion()
        if "降重" in prompt or "相似度" in prompt:
            return MockProvider._mock_option()
        if "润色" in prompt or "polish" in prompt.lower():
            return MockProvider._mock_polish()
        # 默认正文
        return MockProvider._mock_body()

    @staticmethod
    def _mock_body() -> str:
        return (
            "本章围绕研究主题展开深入分析。首先，从理论层面梳理了相关概念的内涵与边界，"
            "明确了研究的基本框架与核心范畴。其次，结合已有文献与研究基础，对研究对象的"
            "现状进行了系统考察，识别出当前存在的主要问题与不足。在此基础上，本文提出"
            "了针对性的改进思路与实施方案，并通过具体案例加以验证。结果表明，所提出的"
            "方法能够有效应对研究中遇到的挑战，具有良好的可行性与推广价值。最后，对本"
            "章内容进行了简要总结，为后续章节的展开奠定了坚实基础。"
        )

    @staticmethod
    def _mock_introduction() -> str:
        return (
            "随着社会经济的快速发展，相关领域的理论与实践研究日益受到关注。"
            "在此背景下，本研究具有重要的理论意义与现实价值。国内外学者对此展开了"
            "大量研究，取得了一系列成果，但仍存在一些亟待解决的问题。本文在现有研究"
            "基础上，从新的视角出发，对相关问题进行深入探讨，以期为该领域的研究贡献"
            "新的思路与方法。文章首先介绍研究背景与意义，继而梳理相关文献，随后阐述"
            "研究设计，最后给出研究结论与展望。"
        )

    @staticmethod
    def _mock_conclusion() -> str:
        return (
            "本文围绕研究问题展开了系统分析，得出以下主要结论：第一，研究揭示了"
            "对象的内在规律与特征；第二，提出的方法在实践中得到了有效验证；第三，"
            "研究成果为相关领域提供了有益参考。当然，本研究仍存在一定局限性，如样"
            "本范围有限、数据获取受限等，有待后续研究进一步完善。未来可以从扩大研"
            "究范围、深化理论分析等方向继续探索。"
        )

    @staticmethod
    def _mock_outline() -> str:
        return json.dumps(
            {
                "title": "论文题目",
                "sections": [
                    {
                        "level": 1,
                        "title": "1 绪论",
                        "word_count": 2000,
                        "children": [
                            {"level": 2, "title": "1.1 研究背景与意义", "word_count": 800},
                            {"level": 2, "title": "1.2 国内外研究现状", "word_count": 800},
                            {"level": 2, "title": "1.3 研究内容与方法", "word_count": 400},
                        ],
                    },
                    {
                        "level": 1,
                        "title": "2 相关理论与技术基础",
                        "word_count": 2000,
                        "children": [
                            {"level": 2, "title": "2.1 核心概念界定", "word_count": 1000},
                            {"level": 2, "title": "2.2 相关技术介绍", "word_count": 1000},
                        ],
                    },
                    {
                        "level": 1,
                        "title": "3 问题分析与方案设计",
                        "word_count": 3000,
                        "children": [
                            {"level": 2, "title": "3.1 现状分析与问题识别", "word_count": 1500},
                            {"level": 2, "title": "3.2 方案设计", "word_count": 1500},
                        ],
                    },
                    {
                        "level": 1,
                        "title": "4 实证分析与效果验证",
                        "word_count": 2000,
                        "children": [
                            {"level": 2, "title": "4.1 实验设计", "word_count": 800},
                            {"level": 2, "title": "4.2 结果分析", "word_count": 1200},
                        ],
                    },
                    {
                        "level": 1,
                        "title": "5 结论与展望",
                        "word_count": 1000,
                        "children": [
                            {"level": 2, "title": "5.1 研究总结", "word_count": 600},
                            {"level": 2, "title": "5.2 未来展望", "word_count": 400},
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _mock_abstract() -> str:
        return json.dumps(
            {
                "chinese": "本研究针对相关领域中的关键问题，采用理论与实践相结合的方法，"
                "通过深入的调研与系统分析，提出了有效的解决方案。实证结果表明，该方案"
                "具有较好的效果与可行性，能够为相关实践提供有价值的参考。",
                "english": "This study addresses key issues in the related field by combining "
                "theory with practice. Through in-depth investigation and systematic "
                "analysis, an effective solution is proposed. The empirical results "
                "demonstrate the effectiveness and feasibility of the proposed approach.",
                "keywords_zh": ["关键词一", "关键词二", "关键词三"],
                "keywords_en": ["keyword1", "keyword2", "keyword3"],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _mock_polish() -> str:
        return (
            "（模拟润色结果）经润色后，原文的表述更加严谨规范，逻辑层次更为清晰，"
            "术语使用符合学术规范。建议在此基础上进一步补充数据支撑与文献引用，"
            "以增强论证的说服力。若需真实润色效果，请在设置中配置 AI 模型 API Key。"
        )

    @staticmethod
    def _mock_option() -> str:
        return (
            "（模拟降重结果）针对原文进行了句式重构与同义替换，在保持核心语义不变"
            "的前提下显著降低了字符级相似度。建议结合上下文对改写结果进行审校，"
            "确保学术表达的准确性。若需真实降重效果，请在设置中配置 AI 模型 API Key。"
        )


class ModelManager:
    """模型管理器"""

    _providers: Dict[str, ModelProvider] = {}
    _configs: Dict[str, ModelConfig] = {}
    _default_provider: Optional[str] = None

    @staticmethod
    def mask_api_key(key: str) -> str:
        """脱敏 API Key：只保留前 3 后 4，中间掩码"""
        if not key:
            return ""
        if len(key) <= 10:
            return key[0] + "*" * (len(key) - 2) + key[-1] if len(key) > 2 else "*" * len(key)
        return key[:3] + "*" * 8 + key[-4:]

    @staticmethod
    def is_masked(key: str) -> bool:
        """判断 key 是否为脱敏值（含 *）"""
        return bool(key and "*" in key)

    @classmethod
    async def initialize(cls):
        """初始化：从数据库加载配置，mock 永远可用"""
        # 基础配置（环境变量）
        cls._configs = {}

        # Ollama（总是可用，因为是本地）
        cls._configs["ollama"] = ModelConfig(
            provider="ollama",
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
        )

        # Mock（永远可用）
        cls._configs["mock"] = ModelConfig(
            provider="mock", base_url="", model="mock-local"
        )

        # 从数据库加载用户配置
        provider_names = ["openai", "zhipu", "deepseek", "paperpass", "custom"]
        for name in provider_names:
            stored = await db.get_config(f"model_{name}")
            if stored:
                try:
                    cfg = json.loads(stored)
                    cls._configs[name] = ModelConfig(
                        provider=name,
                        api_key=cfg.get("api_key", ""),
                        base_url=cfg.get("base_url", ""),
                        model=cfg.get("model", ""),
                    )
                except json.JSONDecodeError:
                    continue

        # 默认提供者
        default = await db.get_config("default_provider", "mock")
        cls._default_provider = default if default in cls._configs else "mock"

    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> ModelProvider:
        """获取模型提供者"""
        name = provider_name or cls._default_provider or "mock"

        if name not in cls._providers:
            config = cls._configs.get(name)
            if not config:
                # 回退到 mock
                config = cls._configs.get("mock")
                if not config:
                    raise ValueError("没有可用的模型配置")

            if name == "ollama":
                cls._providers[name] = OllamaProvider(config.base_url, config.model)
            elif name == "mock":
                cls._providers[name] = MockProvider()
            else:
                base_url = config.base_url or {
                    "openai": "https://api.openai.com/v1",
                    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
                    "deepseek": "https://api.deepseek.com/v1",
                }.get(name, "https://api.openai.com/v1")

                cls._providers[name] = OpenAICompatibleProvider(
                    api_key=config.api_key or "",
                    base_url=base_url,
                    model=config.model,
                )

        return cls._providers[name]

    @classmethod
    def get_default_name(cls) -> str:
        return cls._default_provider or "mock"

    @classmethod
    def get_config(cls, provider: str) -> Optional[ModelConfig]:
        """获取指定 provider 的配置（可能为 None）"""
        return cls._configs.get(provider)

    @classmethod
    async def test_connection(
        cls,
        provider: str,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
    ) -> tuple:
        """测试模型连接：发最小请求验证配置可用，返回 (ok, message, latency_ms)"""
        import time
        start = time.monotonic()
        try:
            if provider == "ollama":
                client = httpx.AsyncClient(timeout=15.0)
                try:
                    resp = await client.get(
                        (base_url or settings.OLLAMA_BASE_URL).rstrip("/") + "/api/tags"
                    )
                    ok = resp.status_code == 200
                    msg = f"Ollama 连接成功" if ok else f"Ollama 响应异常 ({resp.status_code})"
                    return ok, msg, int((time.monotonic() - start) * 1000)
                finally:
                    await client.aclose()

            elif provider == "mock":
                return True, "本地模拟模式（无需测试）", 0

            else:
                # OpenAI 兼容端点
                if not model or not api_key or not base_url:
                    return False, "请填写完整的 API Key、模型名和接口地址", 0
                client = httpx.AsyncClient(timeout=30.0)
                try:
                    resp = await client.post(
                        base_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 5,
                            "stream": False,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                        ms = int((time.monotonic() - start) * 1000)
                        return True, f"连接成功 ({ms}ms)，模型回复: {reply[:40]}", ms
                    else:
                        detail = resp.text[:200]
                        ms = int((time.monotonic() - start) * 1000)
                        return False, f"HTTP {resp.status_code}: {detail}", ms
                finally:
                    await client.aclose()
        except httpx.HTTPError as e:
            ms = int((time.monotonic() - start) * 1000)
            return False, f"网络错误: {e.__class__.__name__} ({ms}ms)，请检查地址是否可达", ms
        except Exception as e:
            ms = int((time.monotonic() - start) * 1000)
            return False, f"测试失败: {e} ({ms}ms)", ms

    @classmethod
    def list_available(cls) -> List[Dict[str, Any]]:
        """列出可用模型"""
        result = []
        for name, config in cls._configs.items():
            provider = cls._providers.get(name)
            try:
                is_ready = provider.validate_config() if provider else (
                    bool(config.api_key) if name != "mock" else True
                )
            except Exception:
                is_ready = False
            result.append(
                {
                    "name": name,
                    "model": config.model,
                    "ready": is_ready,
                    "default": name == cls._default_provider,
                }
            )
        return result

    @classmethod
    async def save_config(cls, provider: str, api_key: str, model: str, base_url: str = "", set_default: bool = True):
        """保存模型配置到数据库（脱敏值视为未变更，保留原 Key）"""
        old = cls._configs.get(provider)
        if cls.is_masked(api_key) and old and old.api_key:
            api_key = old.api_key  # 传入的是脱敏显示值，保留原 Key
        cfg = {"api_key": api_key, "model": model, "base_url": base_url}
        await db.set_config(f"model_{provider}", json.dumps(cfg, ensure_ascii=False))
        if set_default:
            await db.set_config("default_provider", provider)
            cls._default_provider = provider

        # 更新内存配置并重建 provider
        cls._configs[provider] = ModelConfig(
            provider=provider, api_key=api_key, base_url=base_url, model=model
        )
        if provider in cls._providers:
            await cls._providers[provider].close()
            del cls._providers[provider]

    @classmethod
    async def generate_stream(
        cls,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        **params,
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        p = cls.get_provider(provider)
        async for chunk in p.chat(messages, **params):
            yield chunk


# 兼容旧引用
ModelManager.initialize_sync = None