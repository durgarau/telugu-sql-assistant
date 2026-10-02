from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


class AIProviderError(Exception):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class AIProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, messages: list[ChatMessage]) -> str:
        """Return the assistant's reply text, or raise AIProviderError."""

    def close(self) -> None:  # noqa: B027
        pass
