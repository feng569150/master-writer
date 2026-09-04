"""
写作 Agent
论文状态读写（数据库） + Skill/Pipeline 编排执行
"""

import json
import math
import re
from typing import Any, Dict, List, Optional, AsyncGenerator
from backend.app.database import db
from backend.app.agent import executor
from backend.app.agent.pipelines import (
    BUILTIN_PIPELINES,
    resolve_value,
    PipelineError,
)
from backend.app.services.skill_engine import SkillEngine


class WritingAgent:
    """
    论文写作执行器

    流程：加载论文状态 → 按 pipeline 顺序执行步骤 → 保存状态
    状态（state）即为该篇论文的完整上下文：title/outline/sections 等，
    每步执行后直接更新并最终写回数据库，无需额外"记忆"缓存。
    """

    def __init__(self, paper_id: str):
        self.paper_id = paper_id
        self.state: Dict[str, Any] = {}

    # ==================== 状态 ====================

    async def load(self) -> "WritingAgent":
        """从数据库加载论文状态（标题/大纲/章节）"""
        paper = await db.get_paper(self.paper_id)
        if not paper:
            raise ValueError(f"论文 {self.paper_id} 不存在")
        sections = await db.get_sections(self.paper_id)
        self.state = {
            "paper_id": self.paper_id,
            "title": paper.get("title", ""),
            "template_id": paper.get("template_id", "default"),
            "target_words": paper.get("target_words", 8000) or 8000,
            "outline": paper.get("outline"),
            "sections": [
                {
                    "id": s.get("id"),
                    "type": s.get("type", "body"),
                    "title": s.get("title", ""),
                    "content": s.get("content", ""),
                    "order": s.get("order", 0),
                }
                for s in sections
            ],
            "references": None,
        }
        return self

    async def save(self):
        """把状态写回数据库（大纲 + 章节，章节先清空重建）"""
        await db.update_paper(
            self.paper_id,
            title=self.state.get("title", ""),
            outline=self.state.get("outline"),
        )
        existing = await db.get_sections(self.paper_id)
        for s in existing:
            await db.delete_section(s["id"])
        for s in self.state.get("sections", []):
            await db.create_section(
                section_id=s.get("id") or f"sec_{self.paper_id}_{s.get('order', 0)}",
                paper_id=self.paper_id,
                section_type=s.get("type", "body"),
                title=s.get("title", ""),
                content=s.get("content", ""),
                order=s.get("order", 0),
            )

    # ==================== 执行 ====================

    async def run_skill(
        self,
        skill_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        stream: bool = True,
        save_to: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """运行单个 Skill（可选 save_to 指定保存目标）"""
        if not self.state:
            await self.load()

        skill = SkillEngine.get_skill(skill_id)
        output_format = skill.output.format if skill else "text"
        buffer = ""

        async for chunk in executor.execute(skill_id, self.state, inputs or {}, stream):
            buffer += chunk
            yield chunk

        # 保存：优先显式 save_to，其次用 Skill 定义的 auto_save 配置
        target = save_to or (skill.output.save_target if skill and skill.output.auto_save else None)
        if target == "sections" and buffer:
            # 需要章节标题来定位/新建章节（结论/引言/正文等）
            title = (inputs or {}).get("section_title") or "生成内容"
            sec_type = _infer_section_type(title)
            executor.update_section(self.state, sec_type, title, buffer)
            await self.save()
        elif target and buffer:
            executor.save_output(self.state, target, output_format, buffer)
            await self.save()
        elif buffer:
            # 无保存目标：结果仅展示，持久化当前章节状态即可
            await self.save()

    async def run_pipeline(
        self,
        pipeline: Any,
        inputs: Optional[Dict[str, Any]] = None,
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """运行 Pipeline（内置名称或自定义定义 dict）"""
        if not self.state:
            await self.load()

        if isinstance(pipeline, str):
            if pipeline in BUILTIN_PIPELINES:
                steps = BUILTIN_PIPELINES[pipeline].get("steps", [])
                meta = BUILTIN_PIPELINES[pipeline]
            else:
                row = await db.get_pipeline(pipeline)
                if not row:
                    raise PipelineError(f"pipeline `{pipeline}` 不存在（内置或自定义）")
                steps = row["definition"]["steps"]
                meta = {"name": row.get("name", pipeline), "description": row.get("description", "")}
        elif isinstance(pipeline, dict):
            steps = pipeline.get("steps", [])
            meta = {"name": pipeline.get("name", "自定义"), "description": pipeline.get("description", "")}
        else:
            raise PipelineError("pipeline 必须是内置名称或定义对象")

        inputs = inputs or {}
        # 用户输入合并进顶层状态上下文（供 {{inputs.xx}} 使用）
        base_context = {**self.state, "inputs": inputs}

        yield f"\n[PIPELINE] 开始：{meta.get('name', '')}\n"
        async for chunk in self._execute_steps(steps, base_context, stream):
            yield chunk

        await self.save()
        yield f"\n[PIPELINE] 完成：{meta.get('name', '')}\n"

    async def _execute_steps(
        self,
        steps: List[dict],
        context: Dict[str, Any],
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """顺序执行步骤列表（支持 skill 与 loop）"""
        total = len(steps)
        for i, step in enumerate(steps):
            # 每一步前刷新上下文：前序步骤可能已更新 state（如大纲）
            for key in ("outline", "sections", "title", "target_words", "template_id"):
                context[key] = self.state.get(key)
            context["full_text"] = executor.build_full_text(self.state.get("sections", []))

            # 进度
            kind = "skill" if "skill" in step else "loop"
            label = step.get("skill", "循环")
            skill = SkillEngine.get_skill(label) if kind == "skill" else None
            progress = {
                "type": "progress",
                "current": i + 1,
                "total": total,
                "step_type": kind,
                "skill_id": label if kind == "skill" else None,
                "skill_name": skill.name if skill else None,
            }
            yield f"\n[PROGRESS]{json.dumps(progress, ensure_ascii=False)}[/PROGRESS]\n"

            async for chunk in self._execute_step(step, context, stream):
                yield chunk

            yield "\n---STEP_DONE---\n"

    async def _execute_step(
        self,
        step: dict,
        context: Dict[str, Any],
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """执行单个步骤（skill 或 loop）；skill 支持分段续写 repeat"""
        if "skill" in step:
            skill_id = step["skill"]
            skill = SkillEngine.get_skill(skill_id)
            output_format = skill.output.format if skill else "text"

            resolved_inputs = {
                k: resolve_value(v, context) for k, v in (step.get("inputs") or {}).items()
            }

            # 参考文献：自动统计正文引文编号，保证编号一致
            if skill_id == "references" and not resolved_inputs.get("count"):
                n = executor.extract_citations(self.state.get("sections", []))
                resolved_inputs["count"] = n if n > 0 else 5

            save_to = step.get("save_to")

            # 分段续写：repeat 为目标字数 → ceil(words/800) 段
            segments = 1
            if step.get("repeat"):
                try:
                    n = int(resolve_value(step["repeat"], context) or 0)
                    segments = max(1, math.ceil(n / 800))
                except (TypeError, ValueError):
                    segments = 1

            title = resolved_inputs.get("section_title")
            sec_type = _infer_section_type(title) if title else "body"

            for seg in range(segments):
                seg_inputs = dict(resolved_inputs)
                if seg > 0 and title:
                    # 传入本章已有内容，提示 AI 承接续写
                    current = next(
                        (s.get("content", "") for s in self.state.get("sections", [])
                         if s.get("title") == title), "")
                    if current:
                        seg_inputs["last_content"] = current

                buffer = ""
                async for chunk in executor.execute(skill_id, self.state, seg_inputs, stream):
                    buffer += chunk
                    yield chunk

                if save_to and buffer:
                    if save_to == "sections" and title:
                        # 首段覆盖、后续追加（分段续写累计）
                        if seg == 0:
                            executor.update_section(self.state, sec_type, title, buffer)
                        else:
                            executor.append_section(self.state, title, buffer)
                    elif seg == 0:
                        executor.save_output(self.state, save_to, output_format, buffer)

        elif "loop" in step:
            loop = step["loop"]
            items = resolve_value(f"{{{{{loop['over']}}}}}", context) or []
            var_name = loop.get("as", "item")
            for idx, item in enumerate(items):
                loop_context = {
                    **context,
                    var_name: item,
                    f"{var_name}_index": idx,
                }
                if isinstance(item, dict):
                    yield f"\n[LOOP] {idx + 1}/{len(items)}：{item.get('title', '')}\n"
                else:
                    yield f"\n[LOOP] {idx + 1}/{len(items)}\n"
                for sub in loop.get("steps", []):
                    async for chunk in self._execute_step(sub, loop_context, stream):
                        yield chunk


def _infer_section_type(title: str) -> str:
    """根据章节标题推断类型"""
    t = title or ""
    if "引言" in t or "绪论" in t or "introduction" in t.lower():
        return "introduction"
    if "结论" in t or "总结" in t or "conclusion" in t.lower():
        return "conclusion"
    return "body"


async def create_agent(paper_id: str) -> WritingAgent:
    """工厂：创建并加载 Agent"""
    agent = WritingAgent(paper_id)
    await agent.load()
    return agent