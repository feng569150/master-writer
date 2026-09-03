"""
共享测试基础设施
设置临时数据目录，提供公共导入路径
"""

import os
import sys
import tempfile

# 在导入任何 backend 模块前设置临时数据目录
_TMP_DIR = tempfile.mkdtemp(prefix="mw_test_")
os.environ["MW_DATA_DIR"] = _TMP_DIR

# 添加项目根目录到 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 禁用外部网络
os.environ.setdefault("MW_OFFLINE", "1")


def get_tmp_dir() -> str:
    return _TMP_DIR