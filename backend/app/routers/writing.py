"""
写作路由
"""

import uuid
import json
from pydantic import BaseModel
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from backend.app.models.schema import (
    ResponseBase, PaperCreate, PaperUpdate, SectionCreate, 
    SectionUpdate, SkillExecuteRequest, SkillPipelineRequest
)
from backend.app.database import db
from backend.app.services.skill_engine import SkillEngine
from backend.app.agent.agent import WritingAgent, create_agent
from backend.app.agent import pipelines as ppl

router = APIRouter(prefix="/api", tags=["写作"])


# === 论文项目管理 ===

@router.post("/papers")
async def create_paper(req: PaperCreate):
    """创建论文项目"""
    paper_id = str(uuid.uuid4())[:8]
    await db.create_paper(paper_id, req.title, req.template_id)
    return ResponseBase(data={"id": paper_id, "title": req.title})


@router.get("/papers")
async def list_papers():
    """列出所有论文"""
    papers = await db.list_papers()
    return ResponseBase(data=papers)


@router.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    """获取论文详情"""
    paper = await db.get_paper(paper_id)
    if not paper:
        return JSONResponse(status_code=404, content={"success": False, "message": "论文不存在"})
    
    sections = await db.get_sections(paper_id)
    paper["sections"] = sections
    return ResponseBase(data=paper)


@router.put("/papers/{paper_id}")
async def update_paper(paper_id: str, req: PaperUpdate):
    """更新论文"""
    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        return ResponseBase(message="无更新内容")
    
    await db.update_paper(paper_id, **update_data)
    
    # 更新上下文
    if "outline" in update_data:
        SkillEngine.update_context(paper_id, {"outline": update_data["outline"]})
    
    return ResponseBase(message="更新成功")


@router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    """删除论文"""
    await db.delete_paper(paper_id)
    SkillEngine.clear_context(paper_id)
    return ResponseBase(message="删除成功")


# === 章节管理 ===

@router.post("/sections")
async def create_section(req: SectionCreate):
    """创建章节"""
    section_id = str(uuid.uuid4())[:8]
    await db.create_section(
        section_id, req.paper_id, req.type, req.title, req.content, req.order
    )
    return ResponseBase(data={"id": section_id})


@router.get("/papers/{paper_id}/sections")
async def get_sections(paper_id: str):
    """获取论文章节"""
    sections = await db.get_sections(paper_id)
    return ResponseBase(data=sections)


@router.put("/sections/{section_id}")
async def update_section(section_id: str, req: SectionUpdate):
    """更新章节"""
    update_data = req.model_dump(exclude_unset=True)
    await db.update_section(section_id, **update_data)
    return ResponseBase(message="更新成功")


@router.delete("/sections/{section_id}")
async def delete_section(section_id: str):
    """删除章节"""
    await db.delete_section(section_id)
    return ResponseBase(message="删除成功")


# === Skill 执行 ===

@router.get("/skills")
async def list_skills(category: str = None):
    """列出所有 Skill"""
    skills = SkillEngine.list_skills(category)
    return ResponseBase(data=skills)


@router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, req: SkillExecuteRequest):
    """执行单个 Skill（新版 Agent 入口）"""
    if req.stream:
        async def event_generator():
            agent = await create_agent(req.paper_id)
            async for chunk in agent.run_skill(skill_id, req.inputs, stream=True):
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    else:
        agent = await create_agent(req.paper_id)
        result = ""
        async for chunk in agent.run_skill(skill_id, req.inputs, stream=False):
            result += chunk
        
        try:
            data = json.loads(result)
            return ResponseBase(data=data)
        except json.JSONDecodeError:
            return ResponseBase(data={"result": result})


@router.post("/skills/pipeline")
async def run_pipeline(req: SkillPipelineRequest):
    """执行 Skill Pipeline（兼容旧接口，按 skill 列表顺序执行）"""
    def _build_custom_steps(skills: list) -> list:
        return [{"skill": s} for s in skills]

    async def event_generator():
        agent = await create_agent(req.paper_id)
        steps = _build_custom_steps(req.skills)
        async for chunk in agent.run_pipeline({"steps": steps, "name": "自定义"}, {}, stream=True):
            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.post("/agent/pipeline/{pipeline_name}")
async def run_agent_pipeline(pipeline_name: str, req: SkillExecuteRequest):
    """运行 Pipeline（内置名或自定义 ID），支持流式"""
    async def event_generator():
        try:
            agent = await create_agent(req.paper_id)
            async for chunk in agent.run_pipeline(pipeline_name, req.inputs, stream=True):
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'chunk': f'\n[错误] {e}\n'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


# === Pipeline 管理（为自定义编排 UI 提供接口） ===

@router.get("/agent/pipelines")
async def list_pipelines():
    """列出所有 pipeline（内置 + 自定义）"""
    return ResponseBase(data=await ppl.list_pipelines())


class PipelineCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: list


@router.post("/agent/pipelines")
async def create_pipeline(req: PipelineCreate):
    """创建自定义 pipeline"""
    try:
        data = await ppl.save_custom_pipeline(
            req.id.strip(), req.name, req.description, req.steps
        )
        return ResponseBase(data=data, message=f"Pipeline {req.name} 已创建")
    except ppl.PipelineError as e:
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


@router.put("/agent/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: str, req: PipelineCreate):
    """更新自定义 pipeline"""
    try:
        data = await ppl.save_custom_pipeline(
            pipeline_id, req.name, req.description, req.steps
        )
        return ResponseBase(data=data, message=f"Pipeline {req.name} 已更新")
    except ppl.PipelineError as e:
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


@router.delete("/agent/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    """删除自定义 pipeline（内置不可删）"""
    try:
        await ppl.delete_custom_pipeline(pipeline_id)
        return ResponseBase(message=f"Pipeline {pipeline_id} 已删除")
    except ppl.PipelineError as e:
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


# === 通用生成 ===

@router.post("/generate")
async def generate(req: SkillExecuteRequest):
    """通用 AI 生成接口"""
    from backend.app.services.model_provider import ModelManager
    
    async def event_generator():
        messages = [
            {"role": "user", "content": req.inputs.get("prompt", "")}
        ]
        
        async for chunk in ModelManager.generate_stream(
            messages=messages,
            temperature=req.inputs.get("temperature", 0.7),
            max_tokens=req.inputs.get("max_tokens", 2000)
        ):
            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
