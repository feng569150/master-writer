"""
Agent 记忆系统
管理论文写作的上下文状态，包括工作记忆和长期记忆
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from backend.app.database import db


@dataclass
class PaperMemory:
    """论文记忆对象：维护一篇论文的完整上下文"""
    paper_id: str
    title: str = ""
    template_id: str = "default"
    topic: str = ""
    outline: Optional[Dict[str, Any]] = None
    sections: List[Dict[str, Any]] = field(default_factory=list)
    references: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperMemory":
        return cls(**data)
    
    def get_summary(self, max_length: int = 1000) -> str:
        """获取论文摘要，用于上下文注入"""
        parts = []
        if self.title:
            parts.append(f"论文题目：{self.title}")
        if self.outline:
            parts.append(f"大纲：{json.dumps(self.outline, ensure_ascii=False)[:500]}")
        if self.sections:
            for s in self.sections[:3]:
                content = s.get("content", "")
                parts.append(f"{s.get('title', '')}：{content[:200]}...")
        return "\n".join(parts)[:max_length]
    
    def get_section_by_type(self, section_type: str) -> Optional[Dict[str, Any]]:
        """按类型获取章节"""
        for s in self.sections:
            if s.get("type") == section_type:
                return s
        return None
    
    def update_section(self, section_type: str, title: str, content: str):
        """更新或添加章节：优先按类型+标题匹配，其次按标题匹配，最后追加"""
        # 1. 类型 + 标题都匹配
        for s in self.sections:
            if s.get("type") == section_type and s.get("title") == title:
                s["content"] = content
                s["updated_at"] = datetime.now().isoformat()
                return
        # 2. 仅标题匹配（如不同章节类型但同名）
        for s in self.sections:
            if s.get("title") == title:
                s["type"] = section_type
                s["content"] = content
                s["updated_at"] = datetime.now().isoformat()
                return
        # 3. 追加新章节
        self.sections.append({
            "type": section_type,
            "title": title,
            "content": content,
            "order": len(self.sections),
            "updated_at": datetime.now().isoformat()
        })


class MemoryStore:
    """记忆存储：工作内存 + 数据库持久化"""
    
    _memories: Dict[str, PaperMemory] = {}
    
    @classmethod
    async def load(cls, paper_id: str) -> PaperMemory:
        """从数据库加载论文记忆"""
        if paper_id in cls._memories:
            return cls._memories[paper_id]
        
        paper = await db.get_paper(paper_id)
        if not paper:
            raise ValueError(f"论文 {paper_id} 不存在")
        
        sections = await db.get_sections(paper_id)
        
        memory = PaperMemory(
            paper_id=paper_id,
            title=paper.get("title", ""),
            template_id=paper.get("template_id", "default"),
            topic=paper.get("title", ""),
            outline=paper.get("outline"),
            sections=[{
                "id": s.get("id"),
                "type": s.get("type"),
                "title": s.get("title", ""),
                "content": s.get("content", ""),
                "order": s.get("order", 0)
            } for s in sections],
            created_at=paper.get("created_at", ""),
            updated_at=paper.get("updated_at", "")
        )
        
        cls._memories[paper_id] = memory
        return memory
    
    @classmethod
    def get(cls, paper_id: str) -> Optional[PaperMemory]:
        """获取内存中的记忆"""
        return cls._memories.get(paper_id)
    
    @classmethod
    def set(cls, paper_id: str, memory: PaperMemory):
        """设置内存中的记忆"""
        cls._memories[paper_id] = memory
    
    @classmethod
    async def save(cls, paper_id: str):
        """保存记忆到数据库"""
        memory = cls._memories.get(paper_id)
        if not memory:
            return
        
        await db.update_paper(
            paper_id,
            title=memory.title,
            outline=memory.outline
        )
        
        # 保存章节（简化：先删除再重建）
        existing = await db.get_sections(paper_id)
        for s in existing:
            await db.delete_section(s["id"])
        
        for s in memory.sections:
            await db.create_section(
                section_id=s.get("id") or db._generate_id(),
                paper_id=paper_id,
                section_type=s.get("type", "body"),
                title=s.get("title", ""),
                content=s.get("content", ""),
                order=s.get("order", 0)
            )
    
    @classmethod
    def clear(cls, paper_id: str):
        """清除内存中的记忆"""
        cls._memories.pop(paper_id, None)
    
    @classmethod
    async def load_all(cls):
        """加载所有论文到内存（启动时）"""
        papers = await db.list_papers()
        for paper in papers:
            try:
                await cls.load(paper["id"])
            except Exception as e:
                print(f"加载论文记忆失败 {paper['id']}: {e}")


# 辅助方法
def generate_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


# 给 database 增加一个生成 id 的辅助方法
db._generate_id = generate_id
