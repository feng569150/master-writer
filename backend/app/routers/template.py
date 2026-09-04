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
from backend.app.database import db

router = APIRouter(prefix="/api/templates", tags=["模板"])


def _merge_template_config(base: dict, patch: dict) -> dict:
    """深合并模板配置：page/fonts/paragraph 浅合并，headings 需二级合并"""
    result = dict(base)
    # 先合并子对象（基于 base 的完整字段）
    for key in ("page", "fonts", "paragraph"):
        if isinstance(patch.get(key), dict) and isinstance(base.get(key), dict):
            result[key] = {**base[key], **patch[key]}
    # headings 二级合并：每级内部字段合并（只给 font/size 也保持完整）
    if isinstance(patch.get("headings"), dict) and isinstance(base.get("headings"), dict):
        merged_h = {lv: dict(cfg) for lv, cfg in base["headings"].items()}
        for lv, lv_cfg in patch["headings"].items():
            if isinstance(lv_cfg, dict) and lv in merged_h:
                merged_h[lv] = {**merged_h[lv], **lv_cfg}
            else:
                merged_h[lv] = dict(lv_cfg) if isinstance(lv_cfg, dict) else lv_cfg
        result["headings"] = merged_h
    # 顶层其他字段
    for k, v in patch.items():
        if k not in ("page", "fonts", "paragraph", "headings"):
            result[k] = v
    return result


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
async def create_template(req: dict):
    """手动创建自定义模板（基于默认模板补全配置）"""
    try:
        name = str(req.get("name") or "").strip()
        config = req.get("config") or {}
        if not name:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "模板名称不能为空"}
            )
        # 以默认模板为基底，深合并用户配置
        base = TemplateParser.get_default_template()
        base = _merge_template_config(base, config)
        template_id = f"custom_{uuid.uuid4().hex[:8]}"
        base["id"] = template_id
        base["name"] = name
        template = await TemplateEngine.create_custom(template_id, name, base)
        return ResponseBase(data=template.model_dump(), message=f"模板 {name} 已创建")
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"创建失败: {str(e)}"}
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
        config["name"] = file.filename.replace(file_ext, "").rstrip(". .").rstrip() or "自定义模板"
        
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


@router.get("/manage/list")
async def manage_list():
    """模板管理列表（含内置标记）"""
    rows = await TemplateEngine.list_raw()
    result = []
    for r in rows:
        config = r.get("config") or {}
        result.append({
            "id": r["id"],
            "name": r.get("name", config.get("name", r["id"])),
            "description": config.get("description", ""),
            "is_builtin": bool(r.get("is_builtin")),
            "count": len(TemplateEngine.list_all()),
        })
    return ResponseBase(data=result)


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    """删除自定义模板（内置模板不可删除）"""
    try:
        await TemplateEngine.delete_custom(template_id)
        return ResponseBase(message=f"模板 {template_id} 已删除")
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"删除失败: {str(e)}"}
        )


@router.put("/{template_id}")
async def update_template(template_id: str, req: dict):
    """更新自定义模板配置（内置模板不可修改）"""
    try:
        name = str(req.get("name") or "").strip()
        config = req.get("config") or {}
        if not name:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "模板名称不能为空"}
            )
        if not config:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "模板配置不能为空"}
            )
        # 从数据库读取当前配置并合并（保证字段完整）
        existing = await db.get_template(template_id)
        if not existing:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"模板 {template_id} 不存在"}
            )
        merged = existing["config"]
        merged = _merge_template_config(merged, config)
        template = await TemplateEngine.update_custom(template_id, name, merged)
        return ResponseBase(data=template.model_dump(), message=f"模板 {name} 已更新")
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"更新失败: {str(e)}"}
        )
