import httpx

from .base import AIProvider, AIProviderError, ChatMessage

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(AIProvider):
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        max_tokens: int = 600,
        temperature: float = 0.4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "SQL Mitra"},
        )

    def complete(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        try:
            r = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as e:
            raise AIProviderError(f"request failed: {type(e).__name__}") from e
        if r.status_code != 200:
            raise AIProviderError(f"HTTP {r.status_code}")
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise AIProviderError("malformed response") from e
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("empty response")
        return content.strip()

    def close(self) -> None:
        self._client.close()
