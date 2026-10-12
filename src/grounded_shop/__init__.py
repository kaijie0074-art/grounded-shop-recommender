"""grounded_shop：接地式店铺推荐管线。

LLM 只做语言包装，不做事实生成；输出事实性由 guard.py 机械验证。
"""
from .models import GuardEvent, PipelineResult, Shop
from .pipeline import answer_query
from .store import ShopStore

__all__ = ["Shop", "ShopStore", "answer_query", "PipelineResult", "GuardEvent"]
__version__ = "0.1.0"
