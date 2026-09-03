#!/usr/bin/env python3
"""
MasterWriter 一键启动脚本
"""

import sys
import os
import subprocess
import webbrowser
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

def check_dependencies():
    """检查依赖是否已安装"""
    req_file = os.path.join(PROJECT_ROOT, "backend", "requirements.txt")
    if not os.path.exists(req_file):
        print("[ERROR] requirements.txt not found")
        return False
    
    try:
        import fastapi
        import uvicorn
        import docx
        import yaml
        return True
    except ImportError:
        return False

def install_dependencies():
    """安装依赖"""
    print("[INSTALL] Installing dependencies...")
    req_file = os.path.join(PROJECT_ROOT, "backend", "requirements.txt")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req_file],
        capture_output=False
    )
    return result.returncode == 0

def main():
    print("=" * 50)
    print("   MasterWriter - Academic Writing Assistant")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        if input("Dependencies not installed. Install now? (y/n): ").lower() == 'y':
            if not install_dependencies():
                print("[ERROR] Failed to install dependencies")
                sys.exit(1)
        else:
            print("Please install manually: pip install -r backend/requirements.txt")
            sys.exit(1)
    
    print("[OK] Dependencies check passed")
    
    # 启动服务器
    print("[START] Starting server...")
    host = "127.0.0.1"
    port = 8765
    url = f"http://{host}:{port}"
    
    # 延迟打开浏览器
    def open_browser():
        time.sleep(2)
        print(f"[BROWSER] Opening {url}")
        webbrowser.open(url)
    
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 启动 uvicorn
    try:
        import uvicorn
        uvicorn.run(
            "backend.app.main:app",
            host=host,
            port=port,
            reload=False,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[STOP] Server stopped")

if __name__ == "__main__":
    main()
