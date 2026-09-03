"""
MasterWriter 配置管理
支持环境变量和配置文件，本地运行零配置即可使用
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
# 允许通过环境变量覆盖数据目录（测试隔离用）
DATA_DIR = Path(os.environ.get("MW_DATA_DIR", str(PROJECT_ROOT / "data")))
DB_PATH = DATA_DIR / "db.sqlite"
PAPER_LIBRARY_DIR = DATA_DIR / "paper_library"
SKILLS_DIR = Path(__file__).parent.parent / "skills"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
PAPER_LIBRARY_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """应用配置"""
    
    # 基础
    APP_NAME: str = "MasterWriter"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 服务器
    HOST: str = "127.0.0.1"
    PORT: int = 8765
    
    # 数据库
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DB_PATH}"
    
    # AI 模型配置（用户可在前端设置）
    DEFAULT_MODEL_PROVIDER: str = "openai"  # openai | zhipu | ollama | deepseek
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    ZHIPU_API_KEY: str = ""
    ZHIPU_MODEL: str = "glm-4-flash"
    
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5"
    
    # 查重配置
    PLAGIARISM_THRESHOLD: float = 0.3  # 默认相似度阈值
    PLAGIARISM_CHUNK_SIZE: int = 50    # 指纹分块大小（字符数）
    
    # 导出配置
    EXPORT_TEMP_DIR: str = str(DATA_DIR / "temp")
    
    class Config:
        env_file = PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 确保临时目录存在
os.makedirs(settings.EXPORT_TEMP_DIR, exist_ok=True)
