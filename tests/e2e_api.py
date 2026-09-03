"""
端到端 API 集成测试
启动服务 → 创建论文 → 生成大纲 → 生成正文 → 生成摘要 → 导出 docx
使用 MockProvider，无需真实 API Key
"""

import json
import sys
import urllib.request
import io
import os

BASE = "http://127.0.0.1:8765"


def api(method, path, body=None, raw=False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw_data = resp.read()
        return raw_data if raw else json.loads(raw_data)


def sse_collect(url, payload):
    """收集 SSE 流式输出"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    chunks = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            line = line.decode("utf-8", errors="replace").strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    parsed = json.loads(line[6:])
                    if parsed.get("chunk"):
                        chunks.append(parsed["chunk"])
                except json.JSONDecodeError:
                    pass
    return "".join(chunks)


def main():
    print("=" * 50)
    print("MasterWriter 端到端流程测试")
    print("=" * 50)

    # 1. 健康检查
    h = api("GET", "/api/health")
    assert h["status"] == "ok", "健康检查失败"
    print(f"[1/6] 健康检查 OK: {h['templates']} 模板, {h['skills']} skills")
    print(f"      模型: {json.dumps(h['models'], ensure_ascii=False)}")

    # 2. 创建论文
    r = api("POST", "/api/papers", {"title": "基于深度学习的图像识别研究", "template_id": "default"})
    assert r["success"], r
    paper_id = r["data"]["id"]
    print(f"[2/6] 创建论文 OK: id={paper_id}")

    # 3. 生成大纲（SSE）
    out = sse_collect(f"/api/skills/paper_outline/execute", {
        "paper_id": paper_id,
        "inputs": {"topic": "基于深度学习的图像识别研究", "paper_type": "default", "word_count": 10000},
        "stream": True,
    })
    print(f"[3/6] 大纲生成 OK: {len(out)} 字符")
    # 检查大纲是否保存
    paper = api("GET", f"/api/papers/{paper_id}")
    outline = paper["data"].get("outline")
    assert outline, "大纲未保存到论文"
    sections_count = len(outline.get("sections", []))
    print(f"      大纲已保存，{sections_count} 个一级章节")

    # 4. 生成正文（SSE）
    out2 = sse_collect(f"/api/skills/body_writing/execute", {
        "paper_id": paper_id,
        "inputs": {"section_title": "第一章 绪论", "word_count": 1000},
        "stream": True,
    })
    print(f"[4/6] 正文生成 OK: {len(out2)} 字符")

    # 5. 生成摘要（SSE，保存为 abstract 章节）
    sse_collect(f"/api/skills/abstract/execute", {
        "paper_id": paper_id,
        "inputs": {"full_text": out2},
        "stream": True,
    })
    paper2 = api("GET", f"/api/papers/{paper_id}")
    sec_types = [s["type"] for s in paper2["data"]["sections"]]
    print(f"[5/6] 摘要生成 OK: 章节类型={sec_types}")
    assert "abstract" in sec_types, "摘要章节未保存"

    # 6. 导出 docx
    raw = api("POST", "/api/export/docx", {"paper_id": paper_id, "format": "docx"}, raw=True)
    assert len(raw) > 1000, "docx 导出太小"
    with open("e2e_test_output.docx", "wb") as f:
        f.write(raw)
    print(f"[6/6] 导出 Word OK: {len(raw)} 字节 (e2e_test_output.docx)")

    # 7. 查重测试（本地库）
    r = api("POST", "/api/plagiarism/check", {"text": out2[:500], "threshold": 0.3})
    print(f"[7/7] 查重接口 OK: 相似度={r['data']['overall_similarity']}, 匹配={len(r['data']['matches'])} 条")

    print("\n" + "=" * 50)
    print("全部通过！端到端流程可用。")
    print("=" * 50)


if __name__ == "__main__":
    main()