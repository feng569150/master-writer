"""
SQLite 数据库管理
使用 aiosqlite 实现异步操作
"""

import json
import asyncio
import aiosqlite
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.app.config import DB_PATH


class Database:
    """异步数据库管理器"""
    
    def __init__(self):
        self.db_path = str(DB_PATH)
        self._lock = asyncio.Lock()
    
    async def init(self):
        """初始化数据库表结构"""
        async with aiosqlite.connect(self.db_path) as conn:
            # 论文表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    outline TEXT,
                    content TEXT,
                    target_words INTEGER DEFAULT 8000,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 兼容旧库：papers 补充 target_words 列
            async with conn.execute("PRAGMA table_info(papers)") as cur:
                cols = await cur.fetchall()
            if cols and "target_words" not in [c[1] for c in cols]:
                await conn.execute("ALTER TABLE papers ADD COLUMN target_words INTEGER DEFAULT 8000")
            
            # 论文章节表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sections (
                    id TEXT PRIMARY KEY,
                    paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    "order" INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 模板表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config TEXT NOT NULL,
                    is_builtin INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 用户配置表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # 自定义 pipeline 表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pipelines (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    definition TEXT NOT NULL,
                    is_builtin INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 索引
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sections_paper ON sections(paper_id)")
            
            await conn.commit()
    
    async def execute(self, sql: str, parameters: tuple = ()):
        """执行 SQL"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(sql, parameters)
                await db.commit()
    
    async def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict[str, Any]]:
        """查询单条"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(sql, parameters) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
    
    async def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict[str, Any]]:
        """查询多条"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(sql, parameters) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
    
    # === 论文操作 ===
    
    async def create_paper(self, paper_id: str, title: str, template_id: str, outline: dict = None, target_words: int = 8000):
        outline_json = json.dumps(outline, ensure_ascii=False) if outline else None
        await self.execute(
            "INSERT INTO papers (id, title, template_id, outline, target_words) VALUES (?, ?, ?, ?, ?)",
            (paper_id, title, template_id, outline_json, target_words)
        )
    
    async def get_paper(self, paper_id: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone("SELECT * FROM papers WHERE id = ?", (paper_id,))
        if row and row.get("outline"):
            row["outline"] = json.loads(row["outline"])
        return row
    
    async def update_paper(self, paper_id: str, **kwargs):
        allowed = {"title", "template_id", "outline", "content", "target_words"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values())
        # JSON 序列化
        if "outline" in updates and isinstance(updates["outline"], dict):
            values[list(updates.keys()).index("outline")] = json.dumps(updates["outline"], ensure_ascii=False)
        values.append(paper_id)
        
        await self.execute(
            f"UPDATE papers SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values)
        )
    
    async def list_papers(self) -> List[Dict[str, Any]]:
        return await self.fetchall("SELECT * FROM papers ORDER BY updated_at DESC")
    
    async def delete_paper(self, paper_id: str):
        await self.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    
    # === 章节操作 ===
    
    async def create_section(self, section_id: str, paper_id: str, section_type: str, title: str = "", content: str = "", order: int = 0):
        await self.execute(
            "INSERT INTO sections (id, paper_id, type, title, content, \"order\") VALUES (?, ?, ?, ?, ?, ?)",
            (section_id, paper_id, section_type, title, content, order)
        )
    
    async def get_sections(self, paper_id: str) -> List[Dict[str, Any]]:
        return await self.fetchall(
            "SELECT * FROM sections WHERE paper_id = ? ORDER BY \"order\"",
            (paper_id,)
        )
    
    async def update_section(self, section_id: str, **kwargs):
        allowed = {"title", "content", "type", "order"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values())
        values.append(section_id)
        await self.execute(f"UPDATE sections SET {set_clause} WHERE id = ?", tuple(values))
    
    async def delete_section(self, section_id: str):
        await self.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    
    # === 模板操作 ===
    
    async def create_template(self, template_id: str, name: str, config: dict, is_builtin: bool = False):
        await self.execute(
            "INSERT INTO templates (id, name, config, is_builtin) VALUES (?, ?, ?, ?)",
            (template_id, name, json.dumps(config, ensure_ascii=False), 1 if is_builtin else 0)
        )
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone("SELECT * FROM templates WHERE id = ?", (template_id,))
        if row:
            row["config"] = json.loads(row["config"])
        return row
    
    async def list_templates(self) -> List[Dict[str, Any]]:
        rows = await self.fetchall("SELECT * FROM templates ORDER BY is_builtin DESC, name")
        for row in rows:
            row["config"] = json.loads(row["config"])
        return rows

    async def delete_template(self, template_id: str):
        """删除模板（仅允许自定义模板）"""
        row = await self.fetchone("SELECT is_builtin FROM templates WHERE id = ?", (template_id,))
        if row and row.get("is_builtin"):
            raise ValueError(f"内置模板 {template_id} 不可删除")
        await self.execute("DELETE FROM templates WHERE id = ?", (template_id,))

    async def update_template(self, template_id: str, name: str, config: dict):
        """更新自定义模板（内置模板禁止修改）"""
        row = await self.fetchone("SELECT is_builtin FROM templates WHERE id = ?", (template_id,))
        if not row:
            raise ValueError(f"模板 {template_id} 不存在")
        if row.get("is_builtin"):
            raise ValueError(f"内置模板 {template_id} 不可修改")
        await self.execute(
            "UPDATE templates SET name = ?, config = ? WHERE id = ?",
            (name, json.dumps(config, ensure_ascii=False), template_id),
        )
    
    # === 用户配置 ===
    
    async def set_config(self, key: str, value: str):
        await self.execute(
            "INSERT OR REPLACE INTO user_config (key, value) VALUES (?, ?)",
            (key, value)
        )
    
    async def get_config(self, key: str, default: str = "") -> str:
        row = await self.fetchone("SELECT value FROM user_config WHERE key = ?", (key,))
        return row["value"] if row else default
    
    # === 自定义 Pipeline 操作 ===
    
    async def save_pipeline(self, pipeline_id: str, name: str, description: str, definition: dict):
        await self.execute(
            "INSERT OR REPLACE INTO pipelines (id, name, description, definition) VALUES (?, ?, ?, ?)",
            (pipeline_id, name, description, json.dumps(definition, ensure_ascii=False))
        )
    
    async def get_pipeline(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,))
        if row:
            row["definition"] = json.loads(row["definition"])
        return row
    
    async def list_pipelines(self) -> List[Dict[str, Any]]:
        rows = await self.fetchall("SELECT * FROM pipelines ORDER BY created_at DESC")
        for row in rows:
            row["definition"] = json.loads(row["definition"])
        return rows
    
    async def delete_pipeline(self, pipeline_id: str):
        await self.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))


# 全局数据库实例
db = Database()
