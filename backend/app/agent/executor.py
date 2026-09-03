"""
Agent 执行器
执行单个 Skill，处理输入/输出/上下文
"""

import re
import json
from typing import Dict, Any, Optional, AsyncGenerator
from jinja2 import Template
from backend.app.services.model_provider import ModelManager
from backend.app.services.skill_engine import SkillEngine
from backend.app.agent.memory import PaperMemory


class SkillExecutor:
    """Skill 执行器"""
    
    @classmethod
    async def execute(
        cls,
        skill_id: str,
        memory: PaperMemory,
        inputs: Dict[str, Any] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """执行 Skill"""
        skill = SkillEngine.get_skill(skill_id)
        if not skill:
            yield json.dumps({"error": f"Skill {skill_id} 不存在"}, ensure_ascii=False)
            return
        
        inputs = inputs or {}
        
        # 构建变量上下文
        context = cls._build_context(memory)
        
        # 注入 Skill 声明需要的上下文变量
        for var_name in skill.context_vars:
            if var_name in context and var_name not in inputs:
                inputs[var_name] = context[var_name]
        
        # 渲染 Prompt
        prompt = cls._render_prompt(skill.prompt_template, {**context, **inputs})
        system_prompt = skill.system_prompt or "你是一位专业的学术写作助手。"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # 调用模型
        full_response = ""
        model_params = skill.model_params or {}
        
        async for chunk in ModelManager.generate_stream(messages=messages, **model_params):
            full_response += chunk
            if stream:
                yield chunk
        
        # 解析输出
        if not stream:
            yield full_response
        else:
            # 在流结束后，保存最终解析结果到 memory
            try:
                result = cls._parse_output(full_response, skill.output.format)
                cls._update_memory(memory, skill, result)
            except Exception:
                pass
    
    @classmethod
    def execute_sync(
        cls,
        skill_id: str,
        memory: PaperMemory,
        inputs: Dict[str, Any] = None
    ) -> str:
        """同步执行 Skill（用于内部调用）"""
        import asyncio
        
        async def _run():
            result = ""
            async for chunk in cls.execute(skill_id, memory, inputs, stream=False):
                result += chunk
            return result
        
        return asyncio.run(_run())
    
    @classmethod
    def _build_context(cls, memory: PaperMemory) -> Dict[str, Any]:
        """从记忆构建上下文"""
        return {
            "paper_id": memory.paper_id,
            "title": memory.title,
            "topic": memory.topic,
            "outline": memory.outline,
            "sections": memory.sections,
            "references": memory.references,
            "summary": memory.get_summary()
        }
    
    @classmethod
    def _render_prompt(cls, template_str: str, variables: Dict[str, Any]) -> str:
        """渲染 Prompt"""
        # 添加自定义过滤器
        from jinja2 import Environment
        env = Environment()
        env.filters["tojson"] = lambda x, indent=2: json.dumps(x, ensure_ascii=False, indent=indent)
        template = env.from_string(template_str)
        return template.render(**variables)
    
    @classmethod
    def _parse_output(cls, text: str, output_format: str) -> Any:
        """解析输出"""
        if output_format == "json":
            return cls._extract_json(text)
        return text
    
    @classmethod
    def _extract_json(cls, text: str) -> Any:
        """从文本中提取 JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return text
    
    @classmethod
    def _update_memory(cls, memory: PaperMemory, skill, result: Any):
        """根据 Skill 输出配置更新记忆"""
        if not skill.output.auto_save or not skill.output.save_target:
            return
        
        target = skill.output.save_target
        
        if target == "outline":
            memory.outline = result
        elif target == "abstract":
            if isinstance(result, dict):
                # 存为 type=abstract 的章节，方便导出读取
                memory.update_section(
                    "abstract", "摘要", json.dumps(result, ensure_ascii=False)
                )
            else:
                memory.update_section("abstract", "摘要", str(result))
        elif target.startswith("sections."):
            section_title = target.replace("sections.", "")
            if isinstance(result, str):
                # 推断 section 类型
                section_type = "body"
                if "引言" in section_title or "introduction" in section_title.lower():
                    section_type = "introduction"
                elif "结论" in section_title or "conclusion" in section_title.lower():
                    section_type = "conclusion"
                
                memory.update_section(section_type, section_title, result)
