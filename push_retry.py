"""GitHub 网络恢复后自动补推未推送的提交"""
import subprocess, sys, time

for i in range(30):
    r = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    if r.returncode == 0:
        print("[OK] 推送成功")
        sys.exit(0)
    if i % 5 == 0:
        print(f"[{i+1}/30] 网络不可达，等待重试...")
    time.sleep(10)
print("[FAIL] 推送失败，请检查网络后手动执行: git push origin main")
sys.exit(1)
