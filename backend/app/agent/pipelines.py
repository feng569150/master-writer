"""
Pipeline 系统
内置 + 用户自定义写作流程定义、存储、校验与变量解析
"""

import re
import json
from typing import Any, Dict, List, Optional
from backend.app.database import db


# ==================== 内置 Pipeline ====================

BUILTIN_PIPELINES: Dict[str, dict] = {
    "full_paper": {
        "name": "一键成文",
        "description": "大纲 → 各章正文（按目标字数分段续写） → 摘要 → 参考文献",
        "steps": [
            {
                "skill": "paper_outline",
                "inputs": {"word_count": "{{inputs.word_count}}"},
                "save_to": "outline",
            },
            {
                "loop": {
                    "over": "outline.sections",
                    "as": "section",
                    "steps": [
                        {
                            "skill": "body_writing",
                            "inputs": {
                                "section_title": "{{section.title}}",
                                "section_outline": "{{section}}",
                                "word_count": "{{section.word_count}}",
                            },
                            "save_to": "sections",
                            # 按该章目标字数自动分段续写（每段约 800 字）
                            "repeat": "{{section.word_count}}",
                        }
                    ],
                }
            },
            {"skill": "abstract", "inputs": {"word_count": 400}, "save_to": "abstract"},
            {"skill": "references", "save_to": "references"},
        ],
    },
    "outline_only": {
        "name": "仅生成大纲",
        "description": "只生成论文三级大纲",
        "steps": [
            {"skill": "paper_outline", "save_to": "outline"},
        ],
    },
    "polish_paper": {
        "name": "全文润色",
        "description": "对所有章节内容逐章润色",
        "steps": [
            {
                "loop": {
                    "over": "sections",
                    "as": "section",
                    "steps": [
                        {
                            "skill": "polish",
                            "inputs": {"text": "{{section.content}}"},
                            "save_to": "sections",
                        }
                    ],
                }
            },
        ],
    },
}

BUILTIN_PIPELINE_IDS = set(BUILTIN_PIPELINES.keys())


# ==================== 校验与解析 ====================

class PipelineError(ValueError):
    pass


def validate_pipeline(defn: dict) -> None:
    """校验 pipeline 定义结构是否合法"""
    if not isinstance(defn, dict) or not isinstance(defn.get("steps"), list):
        raise PipelineError("pipeline 必须包含 steps 列表")
    for step in defn["steps"]:
        if not isinstance(step, dict):
            raise PipelineError("每个步骤必须是对象")
        if "skill" in step:
            if not isinstance(step["skill"], str) or not step["skill"].strip():
                raise PipelineError("skill 步骤缺少 skill 名称")
        elif "loop" in step:
            loop = step["loop"]
            if not isinstance(loop, dict):
                raise PipelineError("loop 步骤必须包含 loop 配置")
            if not isinstance(loop.get("over"), str) or not isinstance(
                loop.get("steps"), list
            ):
                raise PipelineError("loop 必须包含 over 与 steps")
            # 递归校验子步骤
            sub = {"steps": loop["steps"]}
            validate_pipeline(sub)
        else:
            raise PipelineError("步骤必须是 skill 或 loop 类型")


def resolve_value(expr: Any, context: Dict[str, Any]) -> Any:
    """
    解析表达式值，支持 {{path}} 插值与点路径访问
    例：{{title}} / {{outline.sections}} / {{section.title}} / {{section}}
    """
    if not isinstance(expr, str):
        return expr

    # 完整插值表达式
    if expr.startswith("{{") and expr.endswith("}}"):
        return _get_by_path(expr[2:-2].strip(), context)

    # 字符串内嵌插值
    def _replace(match):
        val = _get_by_path(match.group(1).strip(), context)
        return str(val) if val is not None else ""

    return re.sub(r"\{\{\s*(.+?)\s*\}\}", _replace, expr)


def _get_by_path(path: str, context: Dict[str, Any]) -> Any:
    """按点路径从上下文中取值"""
    value = context
    for part in path.split("."):
        if value is None:
            return None
        if isinstance(value, dict):
            if part in value:
                value = value[part]
            else:
                return None
        elif isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                # 按标题匹配
                value = next(
                    (
                        item
                        for item in value
                        if isinstance(item, dict) and item.get("title") == part
                    ),
                    None,
                )
        else:
            return None
    return value


# ==================== Pipeline 存储（内置 + 用户自定义） ====================

def get_pipeline(pipeline_id: str) -> Optional[dict]:
    """获取 pipeline（内置优先，其次用户自定义）"""
    if pipeline_id in BUILTIN_PIPELINES:
        return {
            "id": pipeline_id,
            "name": BUILTIN_PIPELINES[pipeline_id]["name"],
            "description": BUILTIN_PIPELINES[pipeline_id].get("description", ""),
            "steps": BUILTIN_PIPELINES[pipeline_id]["steps"],
            "is_builtin": True,
        }
    import asyncio

    return asyncio.run(_get_custom(pipeline_id))


async def _get_custom(pipeline_id: str) -> Optional[dict]:
    row = await db.get_pipeline(pipeline_id)
    return row  # None 或已解析的记录


async def list_pipelines() -> List[dict]:
    """列出所有 pipeline（内置 + 自定义）"""
    result = []
    for pid, cfg in BUILTIN_PIPELINES.items():
        result.append(
            {
                "id": pid,
                "name": cfg["name"],
                "description": cfg.get("description", ""),
                "is_builtin": True,
            }
        )
    custom = await db.list_pipelines()
    for row in custom:
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row.get("description", ""),
                "is_builtin": False,
            }
        )
    return result


async def save_custom_pipeline(pipeline_id: str, name: str, description: str, steps: list) -> dict:
    """保存用户自定义 pipeline（新增或覆盖）"""
    if pipeline_id in BUILTIN_PIPELINE_IDS:
        raise PipelineError(f"内置 pipeline {pipeline_id} 不可覆盖")
    definition = {"steps": steps}
    validate_pipeline(definition)
    if not name.strip():
        raise PipelineError("pipeline 名称不能为空")
    await db.save_pipeline(pipeline_id, name.strip(), description, definition)
    return {"id": pipeline_id, "name": name, "description": description, "is_builtin": False}


async def delete_custom_pipeline(pipeline_id: str) -> None:
    """删除用户自定义 pipeline（内置不可删）"""
    if pipeline_id in BUILTIN_PIPELINE_IDS:
        raise PipelineError(f"内置 pipeline {pipeline_id} 不可删除")
    row = await db.get_pipeline(pipeline_id)
    if not row:
        raise PipelineError(f"pipeline {pipeline_id} 不存在")
    await db.delete_pipeline(pipeline_id)