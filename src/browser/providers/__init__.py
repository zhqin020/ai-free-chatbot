from src.browser.providers.base import ProviderAdapter, DefaultProviderAdapter

__all__ = [
    "ProviderAdapter",
    "DefaultProviderAdapter",
]

# NOTE: OpenChatAdapter 未定义，自动降级为 DefaultProviderAdapter，确保可用
from src.browser.providers import DefaultProviderAdapter

class OpenChatAdapter(DefaultProviderAdapter):
    pass
