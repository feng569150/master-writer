"""
配置路由
模型配置、用户设置管理
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend.app.models.schema import ResponseBase, ModelConfig
from backend.app.services.model_provider import ModelManager
from backend.app.database import db

router = APIRouter(prefix="/api/config", tags=["配置"])


class ModelConfigRequest(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    set_default: bool = True


@router.get("/models")
async def list_models():
    """列出所有模型配置与状态"""
    return ResponseBase(data=ModelManager.list_available())


@router.post("/models")
async def save_model(req: ModelConfigRequest):
    """保存模型配置"""
    try:
        await ModelManager.save_config(
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            set_default=req.set_default,
        )
        return ResponseBase(message=f"模型 {req.provider} 配置已保存")
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"配置保存失败: {str(e)}"}
        )


class SettingsRequest(BaseModel):
    key: str
    value: str


@router.get("/{key}")
async def get_setting(key: str):
    """获取单个配置项"""
    value = await db.get_config(key)
    return ResponseBase(data={"key": key, "value": value})


@router.post("/settings")
async def set_setting(req: SettingsRequest):
    """设置配置项"""
    await db.set_config(req.key, req.value)
    return ResponseBase(message="设置已保存")