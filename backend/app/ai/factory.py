import logging

from app.config import Settings

from .base import AIProvider
from .openrouter import OpenRouterProvider

log = logging.getLogger(__name__)


def build_provider(settings: Settings) -> AIProvider | None:
    key = settings.openrouter_api_key
    if key is None or not key.get_secret_value().strip():
        log.info("no OPENROUTER_API_KEY: using canned mentor messages")
        return None
    if not settings.openrouter_model:
        log.warning("OPENROUTER_API_KEY set but OPENROUTER_MODEL missing: using canned mentor")
        return None
    return OpenRouterProvider(
        key.get_secret_value(),
        settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        timeout=settings.ai_timeout_seconds,
    )
