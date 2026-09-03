"""
模板路由
"""

import os
import uuid
import aiofiles
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from backend.app.models.schema import ResponseBase, TemplateConfig
from backend.app.services.template_engine import TemplateEngine
from backend.app.services.template_parser import TemplateParser
from backend.app.config import settings

router = APIRouter(prefix="/api/templates", tags=["模板"])


@router.get("")
async def list_templates():
    """获取所有模板"""
    templates = TemplateEngine.list_all()
    return ResponseBase(data=[t.model_dump() for t in templates])


@router.get("/{template_id}")
async def get_template(template_id: str):
    """获取模板详情"""
    template = TemplateEngine.get(template_id)
    if not template:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": f"模板 {template_id} 不存在"}
        )
    return ResponseBase(data=template.model_dump())


@router.post("")
async def create_template(config: TemplateConfig):
    """创建自定义模板"""
    try:
        template = await TemplateEngine.create_custom(
            config.id,
            config.name,
            config.model_dump()
        )
        return ResponseBase(data=template.model_dump())
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": str(e)}
        )


@router.post("/upload")
async def upload_template(file: UploadFile = File(...)):
    """上传 Word 文档解析为模板"""
    try:
        # 保存上传文件
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext != ".docx":
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "仅支持 .docx 格式"}
            )
        
        temp_path = os.path.join(settings.EXPORT_TEMP_DIR, f"{uuid.uuid4().hex}{file_ext}")
        async with aiofiles.open(temp_path, "wb") as f:
            content = await file.read()
            await f.write(content)
        
        # 解析模板
        config = TemplateParser.parse_docx(temp_path)
        config["id"] = f"custom_{uuid.uuid4().hex[:8]}"
        config["name"] = file.filename.replace(file_ext, "")
        
        # 清理临时文件
        os.remove(temp_path)
        
        # 保存到数据库
        template = await TemplateEngine.create_custom(
            config["id"],
            config["name"],
            config
        )
        
        return ResponseBase(data=template.model_dump())
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"模板解析失败: {str(e)}"}
        )


@router.get("/default")
async def get_default_template():
    """获取默认模板配置"""
    return ResponseBase(data=TemplateParser.get_default_template())
