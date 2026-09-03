"""
Agent 规划器
将用户目标拆解为可执行的 Skill 计划
"""

import yaml
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class StepType(Enum):
    SKILL = "skill"
    LOOP = "loop"
    CONDITION = "condition"
    PARALLEL = "parallel"


@dataclass
class PlanStep:
    """计划步骤"""
    step_type: StepType
    skill_id: Optional[str] = None
    inputs: Dict[str, Any] = None
    save_to: Optional[str] = None
    condition: Optional[str] = None
    loop_var: Optional[str] = None
    loop_items: Optional[str] = None
    steps: List["PlanStep"] = None
    needs: List[str] = None
    
    def __post_init__(self):
        if self.inputs is None:
            self.inputs = {}
        if self.steps is None:
            self.steps = []
        if self.needs is None:
            self.needs = []


class Planner:
    """规划器：根据目标生成执行计划"""
    
    # 预定义的写作 Pipeline
    PIPELINES = {
        "full_paper": [
            {
                "skill": "paper_outline",
                "save_to": "outline"
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
                                "section_outline": "{{section}}"
                            },
                            "save_to": "sections.{{section.title}}"
                        }
                    ]
                }
            },
            {
                "skill": "abstract",
                "needs": ["sections"],
                "save_to": "abstract"
            },
            {
                "skill": "references",
                "needs": ["sections", "outline"],
                "save_to": "references"
            }
        ],
        "outline_only": [
            {
                "skill": "paper_outline",
                "save_to": "outline"
            }
        ],
        "polish_paper": [
            {
                "loop": {
                    "over": "sections",
                    "as": "section",
                    "steps": [
                        {
                            "skill": "polish",
                            "inputs": {
                                "text": "{{section.content}}"
                            },
                            "save_to": "sections.{{section.title}}"
                        }
                    ]
                }
            }
        ]
    }
    
    @classmethod
    def from_pipeline(cls, pipeline_name: str) -> List[PlanStep]:
        """从预定义 Pipeline 生成计划"""
        steps = cls.PIPELINES.get(pipeline_name, [])
        return cls._parse_steps(steps)
    
    @classmethod
    def from_yaml(cls, yaml_text: str) -> List[PlanStep]:
        """从 YAML 文本生成计划"""
        data = yaml.safe_load(yaml_text)
        steps = data.get("pipeline", []) if isinstance(data, dict) else data
        return cls._parse_steps(steps)
    
    @classmethod
    def _parse_steps(cls, steps: List[Dict[str, Any]]) -> List[PlanStep]:
        """解析步骤配置"""
        result = []
        for step in steps:
            if "skill" in step:
                result.append(PlanStep(
                    step_type=StepType.SKILL,
                    skill_id=step["skill"],
                    inputs=step.get("inputs", {}),
                    save_to=step.get("save_to"),
                    needs=step.get("needs", [])
                ))
            elif "loop" in step:
                loop_cfg = step["loop"]
                result.append(PlanStep(
                    step_type=StepType.LOOP,
                    loop_items=loop_cfg.get("over"),
                    loop_var=loop_cfg.get("as"),
                    steps=cls._parse_steps(loop_cfg.get("steps", []))
                ))
            elif "condition" in step:
                result.append(PlanStep(
                    step_type=StepType.CONDITION,
                    condition=step["condition"],
                    steps=cls._parse_steps(step.get("steps", []))
                ))
            elif "parallel" in step:
                result.append(PlanStep(
                    step_type=StepType.PARALLEL,
                    steps=cls._parse_steps(step.get("parallel", []))
                ))
        return result
    
    @classmethod
    def resolve_value(cls, expr: Any, context: Dict[str, Any]) -> Any:
        """解析表达式值，支持 {{var}} 和简单路径"""
        if not isinstance(expr, str):
            return expr
        
        import re
        
        # 处理完整表达式 {{var}}
        if expr.startswith("{{") and expr.endswith("}}"):
            path = expr[2:-2].strip()
            return cls._get_value_by_path(path, context)
        
        # 处理字符串中的变量插值
        def replace_var(match):
            path = match.group(1).strip()
            val = cls._get_value_by_path(path, context)
            return str(val) if val is not None else ""
        
        return re.sub(r"\{\{\s*(.+?)\s*\}\}", replace_var, expr)
    
    @classmethod
    def _get_value_by_path(cls, path: str, context: Dict[str, Any]) -> Any:
        """根据点路径获取值"""
        parts = path.split(".")
        value = context
        for part in parts:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                try:
                    idx = int(part)
                    value = value[idx] if 0 <= idx < len(value) else None
                except ValueError:
                    # 尝试按标题匹配
                    value = next((item for item in value if isinstance(item, dict) and item.get("title") == part), None)
            else:
                return None
        return value
