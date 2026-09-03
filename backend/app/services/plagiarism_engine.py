"""
查重引擎
基于 SimHash + MinHash 的本地查重系统
"""

import re
import json
import hashlib
import asyncio
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datasketch import MinHash, MinHashLSH
from backend.app.config import settings
from backend.app.database import db


@dataclass
class TextChunk:
    """文本分块"""
    text: str
    start: int
    end: int
    fingerprint: int = 0


@dataclass
class MatchResult:
    """匹配结果"""
    source_id: str
    source_title: str
    similarity: float
    matched_text: str
    source_text: str
    start_pos: int
    end_pos: int


class PlagiarismEngine:
    """查重引擎"""
    
    def __init__(self):
        self.chunk_size = settings.PLAGIARISM_CHUNK_SIZE
        self.threshold = settings.PLAGIARISM_THRESHOLD
        self._lsh = None
        self._minhashes: Dict[str, List[Tuple[str, MinHash]]] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化：从数据库加载所有文档指纹"""
        if self._initialized:
            return
        
        # 初始化 LSH
        self._lsh = MinHashLSH(threshold=self.threshold, num_perm=128)
        
        # 加载已有文档
        docs = await db.fetchall("SELECT id, title, fingerprint FROM paper_library")
        for doc in docs:
            fp = json.loads(doc["fingerprint"]) if doc.get("fingerprint") else {}
            minhash_values = fp.get("minhash", [])
            if minhash_values:
                mh = MinHash(num_perm=128)
                mh.update_batch([bytes(v) for v in minhash_values])
                self._lsh.insert(doc["id"], mh)
                self._minhashes[doc["id"]] = [(doc["title"], mh)]
        
        self._initialized = True
    
    def _tokenize(self, text: str) -> List[str]:
        """中文分词（简化版：按字符和标点分词）"""
        # 清洗文本
        text = re.sub(r'\s+', '', text)
        # 按 n-gram 分词
        n = 3
        return [text[i:i+n] for i in range(len(text) - n + 1)] if len(text) >= n else [text]
    
    def _create_minhash(self, text: str) -> MinHash:
        """为文本创建 MinHash"""
        mh = MinHash(num_perm=128)
        tokens = self._tokenize(text)
        for token in tokens:
            mh.update(token.encode('utf-8'))
        return mh
    
    def _create_chunks(self, text: str) -> List[TextChunk]:
        """将文本分块"""
        chunks = []
        # 按句子分块
        sentences = re.split(r'[。！？.!?\n]', text)
        current_pos = 0
        
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 10:  # 太短的句子跳过
                current_pos += len(sent) + 1
                continue
            
            start = current_pos
            end = current_pos + len(sent)
            
            # 创建 MinHash
            mh = self._create_minhash(sent)
            fp = hashlib.md5(sent.encode()).hexdigest()
            
            chunks.append(TextChunk(
                text=sent,
                start=start,
                end=end,
                fingerprint=int(fp, 16) & 0xFFFFFFFFFFFFFFFF
            ))
            current_pos = end + 1
        
        return chunks
    
    async def add_document(self, doc_id: str, title: str, content: str) -> Dict:
        """添加文档到查重库"""
        await self.initialize()
        
        # 创建指纹
        mh = self._create_minhash(content)
        chunks = self._create_chunks(content)
        
        fingerprint = {
            "minhash": [int(x) for x in mh.digest()],
            "chunks": [{"text": c.text, "start": c.start, "end": c.end, "fp": int(c.fingerprint)} for c in chunks]
        }
        
        # 保存到数据库
        await db.add_to_library(doc_id, title, content, fingerprint)
        
        # 添加到 LSH
        self._lsh.insert(doc_id, mh)
        self._minhashes[doc_id] = [(title, mh)]
        
        return fingerprint
    
    async def check(self, text: str, threshold: float = None) -> Dict:
        """查重主入口"""
        await self.initialize()
        
        threshold = threshold or self.threshold
        
        # 创建待查文本的指纹
        text_mh = self._create_minhash(text)
        text_chunks = self._create_chunks(text)
        
        # LSH 查询候选文档
        candidate_ids = self._lsh.query(text_mh)
        
        matches: List[MatchResult] = []
        checked_sentences = set()
        
        for doc_id in candidate_ids:
            doc = await db.get_library_doc(doc_id)
            if not doc:
                continue
            
            # 精确比对
            doc_chunks = self._create_chunks(doc["content"])
            
            for tc in text_chunks:
                if tc.text in checked_sentences:
                    continue
                
                best_match = None
                best_sim = 0.0
                
                for dc in doc_chunks:
                    # 计算相似度（基于字符重叠）
                    sim = self._calculate_similarity(tc.text, dc.text)
                    
                    if sim > threshold and sim > best_sim:
                        best_sim = sim
                        best_match = dc
                
                if best_match and best_sim > threshold:
                    checked_sentences.add(tc.text)
                    matches.append(MatchResult(
                        source_id=doc_id,
                        source_title=doc["title"] or "未知来源",
                        similarity=round(best_sim, 3),
                        matched_text=tc.text,
                        source_text=best_match.text,
                        start_pos=tc.start,
                        end_pos=tc.end
                    ))
        
        # 计算总体相似度
        total_chars = len(text.replace(' ', '').replace('\n', ''))
        matched_chars = sum(m.end_pos - m.start_pos for m in matches)
        overall_similarity = round(matched_chars / total_chars, 4) if total_chars > 0 else 0.0
        
        # 合并相邻的匹配
        merged_matches = self._merge_matches(matches)
        
        return {
            "overall_similarity": overall_similarity,
            "checked_length": total_chars,
            "matches": [
                {
                    "source_id": m.source_id,
                    "source_title": m.source_title,
                    "similarity": m.similarity,
                    "matched_text": m.matched_text,
                    "source_text": m.source_text,
                    "start_pos": m.start_pos,
                    "end_pos": m.end_pos
                }
                for m in merged_matches
            ]
        }
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度（基于字符集重叠）"""
        if not text1 or not text2:
            return 0.0
        
        # 使用 2-gram 计算
        def get_ngrams(text, n=2):
            return set(text[i:i+n] for i in range(len(text) - n + 1))
        
        ngrams1 = get_ngrams(text1)
        ngrams2 = get_ngrams(text2)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        
        return intersection / union if union > 0 else 0.0
    
    def _merge_matches(self, matches: List[MatchResult]) -> List[MatchResult]:
        """合并相邻或重叠的匹配"""
        if not matches:
            return []
        
        # 按位置排序
        sorted_matches = sorted(matches, key=lambda m: (m.start_pos, m.end_pos))
        
        merged = [sorted_matches[0]]
        for current in sorted_matches[1:]:
            last = merged[-1]
            
            # 如果相邻或重叠，且来源相同，合并
            if current.start_pos <= last.end_pos + 10 and current.source_id == last.source_id:
                # 扩展范围
                merged[-1] = MatchResult(
                    source_id=last.source_id,
                    source_title=last.source_title,
                    similarity=max(last.similarity, current.similarity),
                    matched_text=last.matched_text + current.matched_text,
                    source_text=last.source_text,
                    start_pos=last.start_pos,
                    end_pos=max(last.end_pos, current.end_pos)
                )
            else:
                merged.append(current)
        
        return merged


# 全局实例
plagiarism_engine = PlagiarismEngine()
