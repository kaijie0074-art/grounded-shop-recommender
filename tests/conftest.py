"""pytest 公共夹具：路径与店铺库。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from grounded_shop import ShopStore  # noqa: E402


@pytest.fixture(scope="session")
def store() -> ShopStore:
    return ShopStore.load(ROOT / "data" / "shops.json")
