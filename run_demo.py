"""python -m grounded_shop 支持从仓库根直接运行：src 布局需要先注册 src 路径。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from grounded_shop.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
