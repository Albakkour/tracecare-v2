from __future__ import annotations

from app.core.config import Settings
from app.llm.base import LLMProvider, ProviderError
from app.llm.demo_provider import DemoProvider


def get_provider(requested: str | None, settings: Settings) -> LLMProvider:
    """Resolve a provider from an allow-list. Model names are never taken from the request."""
    name = requested or settings.default_provider()
    if name is None:
        raise ProviderError("not_configured", "No analysis provider is configured on the server.", 503)
    if name == "demo":
        if not settings.demo_mode_enabled:
            raise ProviderError("demo_disabled", "Demo mode is disabled on this server.", 400)
        return DemoProvider()
    if name == "anthropic":
        if not settings.anthropic_configured:
            raise ProviderError(
                "not_configured",
                "The Claude provider is not configured: ANTHROPIC_API_KEY is not set on the server. "
                "Use the demo provider, or add an API key (API credit is billed separately from a Claude "
                "subscription — check Anthropic Console).", 400)
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    raise ProviderError("unknown_provider", f"Unknown provider '{name}'.", 400)
