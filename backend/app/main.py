"""
MasterWriter FastAPI 主入口
"""

import os
import sys

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from backend.app.config import settings
from backend.app.database import db
from backend.app.services.template_engine import TemplateEngine
from backend.app.services.skill_engine import SkillEngine
from backend.app.services.model_provider import ModelManager
from backend.app.routers import template, writing, export, config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("[START] MasterWriter starting...")
    
    # 初始化数据库
    await db.init()
    print("[INIT] Database ready")
    
    # 加载模板
    await TemplateEngine.initialize()
    print(f"[INIT] Loaded {len(TemplateEngine.list_all())} templates")
    
    # 加载 Skill
    SkillEngine.load_skills()
    print(f"[INIT] Loaded {len(SkillEngine.list_skills())} skills")
    
    # 初始化 Agent 记忆系统
    print("[INIT] Agent engine ready")
    
    # 初始化模型
    await ModelManager.initialize()
    print("[INIT] Model manager ready", ModelManager.list_available())
    
    print(f"[READY] MasterWriter at http://{settings.HOST}:{settings.PORT}")
    
    yield
    
    # 关闭时
    print("[STOP] MasterWriter shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="本地智能论文写作助手",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request, call_next):
    """静态资源禁用缓存，确保每次改版后浏览器立即获取最新 JS/CSS"""
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response

# 注册路由
app.include_router(template.router)
app.include_router(writing.router)
app.include_router(export.router)
app.include_router(config.router)

# 静态文件（前端）
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def root():
    """首页"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "MasterWriter API 运行中", "version": settings.VERSION}


@app.get("/api/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "templates": len(TemplateEngine.list_all()),
        "skills": len(SkillEngine.list_skills()),
        "models": ModelManager.list_available()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
