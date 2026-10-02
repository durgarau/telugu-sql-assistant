from collections.abc import Callable

from app.ai.base import AIProvider, AIProviderError, ChatMessage


class FakeProvider(AIProvider):
    """Records every prompt; replies via a function of the messages."""

    name = "fake"

    def __init__(self, reply: Callable[[list[ChatMessage]], str] | str = "AI hint ____"):
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return self.reply(messages) if callable(self.reply) else self.reply


class FailingProvider(AIProvider):
    name = "failing"

    def complete(self, messages: list[ChatMessage]) -> str:
        raise AIProviderError("HTTP 503")


def start(client, qid="where-cancelled-orders"):
    r = client.post("/attempts", json={"learner_id": "test-learner", "question_id": qid})
    assert r.status_code == 201, r.text
    return r.json()


def event(client, attempt_id, name, **extra):
    return client.post(f"/attempts/{attempt_id}/events", json={"event": name, **extra})
