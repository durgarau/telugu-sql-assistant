import os
from typing import Any

import httpx

DEFAULT_API_URL = "http://localhost:8780"


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class Api:
    """Thin client for the SQL Mitra API. Takes any httpx.Client, so tests can
    pass FastAPI's TestClient and run the real backend in-process."""

    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def _call(self, method: str, path: str, **kwargs) -> Any:
        try:
            r = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise ApiError(
                "api_unreachable",
                "SQL Mitra server తో connect అవ్వలేకపోయాం. Backend run అవుతోందో check చేయండి.",
            ) from e
        if r.status_code < 400:
            return r.json()
        detail = (
            r.json().get("detail")
            if r.headers.get("content-type", "").startswith("application/json")
            else None
        )
        if isinstance(detail, dict) and "code" in detail:
            raise ApiError(detail["code"], detail["message"], r.status_code)
        raise ApiError(
            "http_error", f"Server error ({r.status_code}). మళ్ళీ try చేయండి.", r.status_code
        )

    def questions(self) -> list[dict]:
        return self._call("GET", "/questions")

    def schema(self) -> list[dict]:
        return self._call("GET", "/practice/schema")

    def start(self, learner_id: str, question_id: str) -> dict:
        return self._call(
            "POST", "/attempts", json={"learner_id": learner_id, "question_id": question_id}
        )

    def send(
        self, attempt_id: str, event: str, *, sql: str | None = None, confirmed: bool = False
    ) -> dict:
        body: dict[str, Any] = {"event": event, "confirmed": confirmed}
        if sql is not None:
            body["sql"] = sql
        return self._call("POST", f"/attempts/{attempt_id}/events", json=body)


def default_api() -> Api:
    base_url = os.environ.get("SQL_MITRA_API_URL", DEFAULT_API_URL)
    return Api(httpx.Client(base_url=base_url, timeout=30.0))
