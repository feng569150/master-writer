"""
Agent Core
轻量级论文写作 Agent，支持记忆、规划、执行、反思 Loop
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from backend.app.agent.memory import MemoryStore, PaperMemory
from backend.app.agent.planner import Planner, PlanStep, StepType
from backend.app.agent.executor import SkillExecutor
from backend.app.services.skill_engine import SkillEngine


class WritingAgent:
    """
    论文写作 Agent
    
    核心 Loop:
    1. Observe: 加载记忆和输入
    2. Plan: 根据目标生成执行计划
    3. Execute: 执行计划中的 Skill
    4. Reflect: 对结果进行质量反思
    5. Iterate: 如需改进，继续执行
    """
    
    def __init__(self, paper_id: str):
        self.paper_id = paper_id
        self.memory: Optional[PaperMemory] = None
    
    async def load(self):
        """加载论文记忆"""
        self.memory = await MemoryStore.load(self.paper_id)
        return self
    
    async def run_skill(
        self,
        skill_id: str,
        inputs: Dict[str, Any] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """运行单个 Skill"""
        if not self.memory:
            await self.load()
        
        async for chunk in SkillExecutor.execute(skill_id, self.memory, inputs or {}, stream):
            yield chunk
        
        # 保存记忆
        await MemoryStore.save(self.paper_id)
    
    async def run_pipeline(
        self,
        pipeline_name: str,
        inputs: Dict[str, Any] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """运行预定义 Pipeline"""
        if not self.memory:
            await self.load()
        
        plan = Planner.from_pipeline(pipeline_name)
        async for chunk in self._execute_plan(plan, inputs or {}, stream):
            yield chunk
    
    async def _execute_plan(
        self,
        steps: List[PlanStep],
        inputs: Dict[str, Any],
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """执行计划"""
        if not self.memory:
            await self.load()
        
        context = self._build_context()
        context.update(inputs)
        
        total_steps = len(steps)
        
        for i, step in enumerate(steps):
            # 发送进度
            progress = {
                "type": "progress",
                "current": i + 1,
                "total": total_steps,
                "step_type": step.step_type.value
            }
            if step.skill_id:
                skill = SkillEngine.get_skill(step.skill_id)
                progress["skill_id"] = step.skill_id
                progress["skill_name"] = skill.name if skill else step.skill_id
            yield f"\n[PROGRESS]{json.dumps(progress, ensure_ascii=False)}[/PROGRESS]\n"
            
            # 执行步骤
            async for chunk in self._execute_step(step, context, stream):
                yield chunk
            
            yield "\n---STEP_DONE---\n"
        
        # 保存记忆
        await MemoryStore.save(self.paper_id)
    
    async def _execute_step(
        self,
        step: PlanStep,
        context: Dict[str, Any],
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """执行单个计划步骤"""
        if step.step_type == StepType.SKILL:
            # 解析输入
            resolved_inputs = {}
            for key, val in step.inputs.items():
                resolved_inputs[key] = Planner.resolve_value(val, context)
            
            async for chunk in SkillExecutor.execute(
                step.skill_id,
                self.memory,
                resolved_inputs,
                stream
            ):
                yield chunk
            
            # 如果需要保存，更新 context
            if step.save_to:
                # 简化处理：只支持保存到 outline/abstract/sections.xxx
                pass
        
        elif step.step_type == StepType.LOOP:
            items = Planner.resolve_value(f"{{{{{step.loop_items}}}}}", context)
            if not items:
                yield f"\n[警告] 循环变量 {step.loop_items} 为空\n"
                return
            
            for idx, item in enumerate(items):
                loop_context = {
                    **context,
                    step.loop_var: item,
                    f"{step.loop_var}_index": idx
                }
                yield f"\n[LOOP] 处理 {step.loop_var} #{idx + 1}: {item.get('title') if isinstance(item, dict) else item}\n"
                
                for sub_step in step.steps:
                    async for chunk in self._execute_step(sub_step, loop_context, stream):
                        yield chunk
        
        elif step.step_type == StepType.CONDITION:
            # 简化：条件步骤暂不实现
            yield "\n[条件步骤暂不支持]\n"
        
        elif step.step_type == StepType.PARALLEL:
            # 简化：并行步骤暂不实现
            yield "\n[并行步骤暂不支持]\n"
    
    def _build_context(self) -> Dict[str, Any]:
        """构建执行上下文"""
        if not self.memory:
            return {}
        
        return {
            "paper_id": self.memory.paper_id,
            "title": self.memory.title,
            "topic": self.memory.topic,
            "outline": self.memory.outline,
            "sections": self.memory.sections,
            "references": self.memory.references,
            "summary": self.memory.get_summary()
        }
    
    async def reflect(self, content: str) -> str:
        """反思生成的内容质量"""
        prompt = f"""你是一位严格的学术论文审稿人。请对以下内容进行质量评估，指出问题并给出修改建议。

内容：
{content[:2000]}

请从以下维度评估：
1. 学术规范性
2. 逻辑连贯性
3. 语言表达
4. 是否存在重复或冗余

输出格式（JSON）：
{{
  "score": 1-10,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}}"""
        
        messages = [{"role": "user", "content": prompt}]
        result = ""
        async for chunk in SkillExecutor.execute("polish", self.memory, {"text": content}, stream=False):
            result += chunk
        return result


async def create_agent(paper_id: str) -> WritingAgent:
    """工厂函数：创建并加载 Agent"""
    agent = WritingAgent(paper_id)
    await agent.load()
    return agent
