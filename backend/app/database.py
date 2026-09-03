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
        async with aiosqlite.connect(self.db_path) as db:
            # 论文表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    outline TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 论文章节表
            await db.execute("""
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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config TEXT NOT NULL,
                    is_builtin INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 查重库文档表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS paper_library (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    content TEXT,
                    fingerprint TEXT,
                    metadata TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 用户配置表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # 索引
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sections_paper ON sections(paper_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_paper_library_title ON paper_library(title)")
            
            await db.commit()
    
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
    
    async def create_paper(self, paper_id: str, title: str, template_id: str, outline: dict = None):
        outline_json = json.dumps(outline, ensure_ascii=False) if outline else None
        await self.execute(
            "INSERT INTO papers (id, title, template_id, outline) VALUES (?, ?, ?, ?)",
            (paper_id, title, template_id, outline_json)
        )
    
    async def get_paper(self, paper_id: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone("SELECT * FROM papers WHERE id = ?", (paper_id,))
        if row and row.get("outline"):
            row["outline"] = json.loads(row["outline"])
        return row
    
    async def update_paper(self, paper_id: str, **kwargs):
        allowed = {"title", "template_id", "outline", "content"}
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
    
    # === 查重库操作 ===
    
    async def add_to_library(self, doc_id: str, title: str, content: str, fingerprint: dict, metadata: dict = None):
        await self.execute(
            "INSERT INTO paper_library (id, title, content, fingerprint, metadata) VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, content, json.dumps(fingerprint, ensure_ascii=False), 
             json.dumps(metadata or {}, ensure_ascii=False))
        )
    
    async def get_library_docs(self) -> List[Dict[str, Any]]:
        rows = await self.fetchall("SELECT id, title, metadata, added_at FROM paper_library ORDER BY added_at DESC")
        for row in rows:
            if row.get("metadata"):
                row["metadata"] = json.loads(row["metadata"])
        return rows
    
    async def get_library_doc(self, doc_id: str) -> Optional[Dict[str, Any]]:
        row = await self.fetchone("SELECT * FROM paper_library WHERE id = ?", (doc_id,))
        if row:
            row["fingerprint"] = json.loads(row["fingerprint"]) if row.get("fingerprint") else {}
            row["metadata"] = json.loads(row["metadata"]) if row.get("metadata") else {}
        return row
    
    async def delete_library_doc(self, doc_id: str):
        await self.execute("DELETE FROM paper_library WHERE id = ?", (doc_id,))
    
    # === 用户配置 ===
    
    async def set_config(self, key: str, value: str):
        await self.execute(
            "INSERT OR REPLACE INTO user_config (key, value) VALUES (?, ?)",
            (key, value)
        )
    
    async def get_config(self, key: str, default: str = "") -> str:
        row = await self.fetchone("SELECT value FROM user_config WHERE key = ?", (key,))
        return row["value"] if row else default


# 全局数据库实例
db = Database()
