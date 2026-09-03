"""
Skill 引擎
解析、加载、执行 Skill 定义
"""

import re
import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncGenerator
from jinja2 import Template
from backend.app.config import SKILLS_DIR
from backend.app.models.schema import SkillDefinition, SkillInput, SkillOutput
from backend.app.services.model_provider import ModelManager
from backend.app.database import db


class SkillEngine:
    """Skill 执行引擎"""
    
    _skills: Dict[str, SkillDefinition] = {}
    _contexts: Dict[str, Dict[str, Any]] = {}  # paper_id -> context
    
    @classmethod
    def load_skills(cls):
        """从文件加载所有 Skill"""
        skill_files = list(SKILLS_DIR.glob("*.yaml"))
        
        for sf in skill_files:
            try:
                data = yaml.safe_load(sf.read_text(encoding="utf-8"))
                skill = SkillDefinition(**data)
                cls._skills[skill.id] = skill
                print(f"[SKILL] Loaded: {skill.id} - {skill.name}")
            except Exception as e:
                print(f"[SKILL] Failed to load {sf}: {e}")
    
    @classmethod
    def get_skill(cls, skill_id: str) -> Optional[SkillDefinition]:
        """获取 Skill 定义"""
        return cls._skills.get(skill_id)
    
    @classmethod
    def list_skills(cls, category: str = None) -> List[Dict[str, Any]]:
        """列出所有 Skill"""
        result = []
        for sid, skill in cls._skills.items():
            if category and skill.category != category:
                continue
            result.append({
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "category": skill.category,
                "version": skill.version
            })
        return result
    
    @classmethod
    def get_context(cls, paper_id: str) -> Dict[str, Any]:
        """获取论文上下文"""
        if paper_id not in cls._contexts:
            cls._contexts[paper_id] = {}
        return cls._contexts[paper_id]
    
    @classmethod
    def update_context(cls, paper_id: str, data: Dict[str, Any]):
        """更新上下文"""
        context = cls.get_context(paper_id)
        context.update(data)
    
    @classmethod
    def clear_context(cls, paper_id: str):
        """清除上下文"""
        cls._contexts.pop(paper_id, None)
    
    @classmethod
    async def execute(
        cls,
        skill_id: str,
        paper_id: Optional[str] = None,
        inputs: Dict[str, Any] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """执行 Skill"""
        skill = cls.get_skill(skill_id)
        if not skill:
            yield json.dumps({"error": f"Skill {skill_id} 不存在"}, ensure_ascii=False)
            return
        
        inputs = inputs or {}
        
        # 构建变量字典
        variables = dict(inputs)
        
        # 注入上下文变量
        if paper_id:
            context = cls.get_context(paper_id)
            for var_name in skill.context_vars:
                if var_name in context:
                    variables[var_name] = context[var_name]
        
        # 渲染 Prompt
        prompt = cls._render_prompt(skill.prompt_template, variables)
        system_prompt = skill.system_prompt or "你是一位专业的学术写作助手。"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # 调用模型
        full_response = ""
        model_params = skill.model_params or {}
        
        async for chunk in ModelManager.generate_stream(
            messages=messages,
            **model_params
        ):
            full_response += chunk
            if stream:
                yield chunk
        
        # 解析输出
        try:
            if skill.output.format == "json":
                result = cls._extract_json(full_response)
            else:
                result = full_response
            
            # 自动保存
            if skill.output.auto_save and paper_id:
                await cls._save_result(paper_id, skill.output.save_target, result)
                cls.update_context(paper_id, {skill.output.save_target: result})
            
            if not stream:
                yield json.dumps({"result": result}, ensure_ascii=False)
        except Exception as e:
            if not stream:
                yield json.dumps({"error": str(e), "raw": full_response}, ensure_ascii=False)
    
    @classmethod
    def _render_prompt(cls, template_str: str, variables: Dict[str, Any]) -> str:
        """渲染 Prompt 模板"""
        template = Template(template_str)
        return template.render(**variables)
    
    @classmethod
    def _extract_json(cls, text: str) -> Any:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试从代码块中提取
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试从文本中找 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # 如果都失败，返回原始文本
        return text
    
    @classmethod
    async def _save_result(cls, paper_id: str, target: str, result: Any):
        """保存结果到数据库"""
        if target == "outline":
            await db.update_paper(paper_id, outline=result)
        elif target == "content":
            await db.update_paper(paper_id, content=result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
        elif target == "abstract":
            # 摘要特殊处理
            paper = await db.get_paper(paper_id)
            content = paper.get("content", "") if paper else ""
            if isinstance(result, dict):
                abstract_text = result.get("chinese", "")
                if abstract_text and content:
                    content = f"摘要：{abstract_text}\n\n{content}"
                await db.update_paper(paper_id, content=content)
    
    @classmethod
    async def run_pipeline(
        cls,
        paper_id: str,
        skills: List[str],
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """执行 Skill Pipeline"""
        total = len(skills)
        
        for i, skill_id in enumerate(skills):
            skill = cls.get_skill(skill_id)
            if not skill:
                yield f"\n[错误] Skill {skill_id} 不存在\n"
                continue
            
            # 发送进度
            progress = {
                "type": "progress",
                "skill": skill_id,
                "name": skill.name,
                "current": i + 1,
                "total": total
            }
            yield f"\n[PROGRESS]{json.dumps(progress)}[/PROGRESS]\n"
            
            # 执行 Skill
            async for chunk in cls.execute(skill_id, paper_id, stream=stream):
                yield chunk
            
            yield "\n---\n"


# 初始化时加载
SkillEngine.load_skills()
