"""
外部查重提供者
为需要"知网级"查重的用户提供第三方查重 API 接入
"""

import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from backend.app.config import settings


class ExternalPlagiarismProvider(ABC):
    """外部查重提供者抽象"""
    
    @abstractmethod
    async def check(self, text: str, title: str = "") -> Dict[str, Any]:
        """查重接口"""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """是否已配置"""
        pass


class PaperPassProvider(ExternalPlagiarismProvider):
    """
    PaperPass 查重（示例，需对接实际 API）
    注意：真实 API 需要商务对接，以下为接口占位
    """
    
    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://api.paperpass.com"
    
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def check(self, text: str, title: str = "") -> Dict[str, Any]:
        """提交查重任务并轮询结果"""
        # 这里是示例代码，真实 API 需要替换
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. 提交任务
            submit = await client.post(
                f"{self.base_url}/submit",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"title": title, "content": text}
            )
            submit.raise_for_status()
            task_id = submit.json().get("task_id")
            
            # 2. 轮询结果
            for _ in range(30):
                result = await client.get(
                    f"{self.base_url}/result/{task_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                data = result.json()
                if data.get("status") == "done":
                    return {
                        "provider": "paperpass",
                        "overall_similarity": data.get("similarity", 0),
                        "report_url": data.get("report_url"),
                        "matches": data.get("matches", [])
                    }
                await asyncio.sleep(2)
            
            raise TimeoutError("查重任务超时")


class PlagiarismAPIManager:
    """外部查重 API 管理器"""
    
    _providers: Dict[str, ExternalPlagiarismProvider] = {}
    
    @classmethod
    def register(cls, name: str, provider: ExternalPlagiarismProvider):
        """注册查重提供者"""
        cls._providers[name] = provider
    
    @classmethod
    def get_provider(cls, name: str) -> Optional[ExternalPlagiarismProvider]:
        """获取查重提供者"""
        return cls._providers.get(name)
    
    @classmethod
    def list_available(cls) -> list:
        """列出可用的外部查重服务"""
        return [
            {
                "name": name,
                "configured": provider.is_configured(),
                "description": cls._get_description(name)
            }
            for name, provider in cls._providers.items()
        ]
    
    @classmethod
    def _get_description(cls, name: str) -> str:
        descriptions = {
            "paperpass": "PaperPass 查重（中文论文，需 API Key）",
            "wanfang": "万方检测（中文论文，需商务对接）",
            "turnitin": "Turnitin（英文论文，需机构授权）"
        }
        return descriptions.get(name, "第三方查重服务")
    
    @classmethod
    async def check(cls, provider_name: str, text: str, title: str = "") -> Dict[str, Any]:
        """使用指定提供者查重"""
        provider = cls.get_provider(provider_name)
        if not provider:
            raise ValueError(f"查重提供者 {provider_name} 不存在")
        if not provider.is_configured():
            raise ValueError(f"查重提供者 {provider_name} 未配置 API Key")
        
        return await provider.check(text, title)


# 初始化
import asyncio
# 从配置读取（后续可从数据库读取）
if settings.DEFAULT_MODEL_PROVIDER:
    pass

# 注册示例提供者
PlagiarismAPIManager.register("paperpass", PaperPassProvider())
