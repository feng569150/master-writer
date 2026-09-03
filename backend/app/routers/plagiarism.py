"""
查重路由
"""

import uuid
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from backend.app.models.schema import (
    ResponseBase, PlagiarismCheckRequest, LibraryDocAdd
)
from backend.app.services.plagiarism_engine import plagiarism_engine
from backend.app.services.external_plagiarism import PlagiarismAPIManager
from backend.app.database import db

router = APIRouter(prefix="/api/plagiarism", tags=["查重"])


@router.post("/check")
async def check_plagiarism(req: PlagiarismCheckRequest):
    """查重"""
    try:
        result = await plagiarism_engine.check(req.text, req.threshold)
        return ResponseBase(data=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"查重失败: {str(e)}"}
        )


@router.post("/library")
async def add_to_library(req: LibraryDocAdd):
    """添加文档到查重库"""
    try:
        doc_id = str(uuid.uuid4())[:8]
        await plagiarism_engine.add_document(doc_id, req.title, req.content)
        return ResponseBase(data={"id": doc_id, "title": req.title})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"添加失败: {str(e)}"}
        )


@router.get("/library")
async def list_library():
    """获取查重库列表"""
    docs = await db.get_library_docs()
    return ResponseBase(data=docs)


@router.delete("/library/{doc_id}")
async def delete_library_doc(doc_id: str):
    """从查重库删除"""
    await db.delete_library_doc(doc_id)
    return ResponseBase(message="删除成功")


@router.get("/external/providers")
async def list_external_providers():
    """列出可用的外部查重服务"""
    return ResponseBase(data=PlagiarismAPIManager.list_available())


@router.post("/external/check/{provider_name}")
async def external_check(provider_name: str, req: PlagiarismCheckRequest):
    """使用第三方查重服务"""
    try:
        result = await PlagiarismAPIManager.check(provider_name, req.text, "")
        return ResponseBase(data=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"外部查重失败: {str(e)}"}
        )
