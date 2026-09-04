"""
Skill 执行器
统一执行单个 Skill：注入上下文 → 渲染 Prompt → 流式生成 → 输出解析
"""

import re
import json
from typing import Any, Dict, Optional, AsyncGenerator
from backend.app.services.model_provider import ModelManager
from backend.app.services.skill_engine import SkillEngine


# ==================== 状态工具 ====================

def build_full_text(sections: list) -> str:
    """拼接全文章节内容"""
    return "\n\n".join(s.get("content", "") for s in (sections or []))


def build_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """从论文状态构建 Skill 上下文"""
    return {
        "paper_id": state.get("paper_id"),
        "title": state.get("title", ""),
        "topic": state.get("title", ""),
        "outline": state.get("outline"),
        "sections": state.get("sections", []),
        "references": state.get("references"),
        "full_text": build_full_text(state.get("sections", [])),
    }


def update_section(state: Dict[str, Any], section_type: str, title: str, content: str):
    """更新或添加章节：优先类型+标题匹配，其次标题匹配，最后追加"""
    sections = state.setdefault("sections", [])
    for s in sections:
        if s.get("type") == section_type and s.get("title") == title:
            s["content"] = content
            return
    for s in sections:
        if s.get("title") == title:
            s["type"] = section_type
            s["content"] = content
            return
    sections.append(
        {
            "type": section_type,
            "title": title,
            "content": content,
            "order": len(sections),
        }
    )


def save_output(state: Dict[str, Any], save_to: str, output_format: str, text: str) -> None:
    """按保存目标把生成结果写入论文状态"""
    # 解析输出（JSON 或纯文本）
    result = _parse_output(text, output_format)

    if save_to == "outline":
        state["outline"] = result if isinstance(result, (dict, list)) else None
    elif save_to == "abstract":
        if isinstance(result, dict):
            update_section(state, "abstract", "摘要", json.dumps(result, ensure_ascii=False))
        else:
            update_section(state, "abstract", "摘要", str(result))
    elif save_to == "references":
        if isinstance(result, list):
            update_section(state, "references", "参考文献", json.dumps(result, ensure_ascii=False))
        elif isinstance(result, dict):
            refs = result.get("references", result)
            update_section(state, "references", "参考文献", json.dumps(refs, ensure_ascii=False))
        else:
            update_section(state, "references", "参考文献", str(result))
    elif save_to == "sections":
        # 需要从输入中得知章节标题/类型，由调用方传入（正文/润色）
        _save_as_section(state, result)
    elif save_to and save_to.startswith("sections."):
        title = save_to.replace("sections.", "")
        update_section(state, "body", title, str(result))
    # 其他 save_to 忽略


def _save_as_section(state: Dict[str, Any], result: Any):
    """sections 目标：结果可能是 dict（{title, content, type}）或字符串"""
    if isinstance(result, dict) and result.get("title") and result.get("content"):
        update_section(state, result.get("type", "body"), result["title"], result["content"])
    elif isinstance(result, str) and result.strip():
        # 无标题信息则覆盖最后一个 body 章节（润色场景由调用方直接处理）
        sections = state.get("sections", [])
        if sections:
            sections[-1]["content"] = str(result)
        else:
            update_section(state, "body", "正文", str(result))


# ==================== 输出解析 ====================

def _parse_output(text: str, output_format: str) -> Any:
    if output_format == "json":
        return _extract_json(text)
    return text


def _extract_json(text: str) -> Any:
    """从文本中提取 JSON（直接解析 / 代码块 / 大括号片段）"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return text


# ==================== 执行 ====================

async def execute(
    skill_id: str,
    state: Dict[str, Any],
    inputs: Optional[Dict[str, Any]] = None,
    stream: bool = True,
) -> AsyncGenerator[str, None]:
    """执行 Skill 并流式返回生成内容"""
    skill = SkillEngine.get_skill(skill_id)
    if not skill:
        yield json.dumps({"error": f"Skill {skill_id} 不存在"}, ensure_ascii=False)
        return

    inputs = dict(inputs or {})
    context = build_context(state)

    # 注入 Skill 声明需要的上下文变量（未显式提供时）
    for var_name in skill.context_vars or []:
        if var_name in context and var_name not in inputs:
            inputs[var_name] = context[var_name]

    # 渲染 Prompt
    from jinja2 import Environment
    env = Environment()
    env.filters["tojson"] = lambda x, indent=2: json.dumps(x, ensure_ascii=False, indent=indent)
    variables = {**context, **inputs}
    prompt = env.from_string(skill.prompt_template).render(**variables)
    system_prompt = skill.system_prompt or "你是一位专业的学术写作助手。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    model_params = skill.model_params or {}
    async for chunk in ModelManager.generate_stream(messages=messages, **model_params):
        yield chunk