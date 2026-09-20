"""
TypeSafe SystemOne (Jev) HTTP client.

Classification only. This module never writes replies and never performs
X actions (like, bookmark, reply, repost, follow, DM, delete).

Auth: TYPESAFE_API_KEY is read from the environment only. The key is never
logged, printed, or written to disk.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)

SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
DEFAULT_MAX_RETRIES = 3
RETRY_STATUS_CODES = frozenset({429, 529})

logger = logging.getLogger(__name__)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class JevSettings(BaseModel):
    """Runtime config sourced from the environment."""

    api_key: str = ""
    model: str = DEFAULT_MODEL
    confidence_threshold: float = 0.85
    shadow_mode: bool = True
    allow_save: bool = False
    endpoint: str = SYSTEMONE_URL

    @classmethod
    def from_env(cls) -> "JevSettings":
        raw_threshold = os.getenv("JEV_CONFIDENCE_THRESHOLD", "0.85")
        try:
            threshold = float(raw_threshold)
        except ValueError:
            threshold = 0.85
        return cls(
            api_key=os.getenv("TYPESAFE_API_KEY", ""),
            model=os.getenv("TYPESAFE_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
            confidence_threshold=threshold,
            shadow_mode=_as_bool(os.getenv("JEV_SHADOW_MODE"), True),
            allow_save=_as_bool(os.getenv("JEV_ALLOW_SAVE"), False),
        )

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())


class JevError(Exception):
    """Base error for the Jev client. Message must never contain secrets."""


class JevConfigError(JevError):
    """Missing or invalid configuration (for example no API key)."""


class JevAPIError(JevError):
    """HTTP or transport failure talking to TypeSafe."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JevParseError(JevError):
    """Response was not valid JSON or did not match the expected schema."""


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float
    probabilities: dict[str, float] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class ScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float
    confidence: float
    legend: dict[str, str] = Field(default_factory=dict)
    probabilities: dict[str, float] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float

    model_config = {"extra": "ignore"}


JevAnswer = Annotated[
    Union[ChoiceAnswer, ScoreAnswer, NoulAnswer],
    Field(discriminator="type"),
]


class JevResponse(BaseModel):
    model: str
    answers: dict[str, JevAnswer]
    usage: dict[str, Any] | None = None

    model_config = {"extra": "ignore"}


class JevCallResult(BaseModel):
    """Successful or failed classify call, with latency for JSONL logs."""

    ok: bool
    response: JevResponse | None = None
    latency_ms: float = 0.0
    error: str | None = None
    status_code: int | None = None
    attempts: int = 1


def _redact_headers(headers: dict[str, str] | httpx.Headers) -> dict[str, str]:
    """Return headers safe to log (Authorization stripped)."""
    safe: dict[str, str] = {}
    for key, value in dict(headers).items():
        if key.lower() == "authorization":
            safe[key] = "Bearer [redacted]"
        else:
            safe[key] = value
    return safe


class JevClient:
    """httpx client for POST https://api.typesafe.ai/v1/systemone."""

    def __init__(
        self,
        settings: JevSettings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: httpx.Timeout | float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or JevSettings.from_env()
        self._transport = transport
        self.timeout = timeout if timeout is not None else httpx.Timeout(15.0, connect=5.0)
        self.max_retries = max_retries
        self._sleep = sleeper

    def _http(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def classify(
        self,
        state: dict[str, Any],
        questions: dict[str, Any],
        *,
        model: str | None = None,
    ) -> JevCallResult:
        """POST a SystemOne classify request. Never mutates X."""
        if not self.settings.has_api_key:
            return JevCallResult(
                ok=False,
                error="TYPESAFE_API_KEY is not set in the environment",
                latency_ms=0.0,
                attempts=0,
            )

        payload = {
            "state": state,
            "model": model or self.settings.model,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        started = time.perf_counter()
        last_error = "unknown error"
        last_status: int | None = None
        attempts = 0

        try:
            with self._http() as client:
                for attempt in range(self.max_retries + 1):
                    attempts = attempt + 1
                    try:
                        response = client.post(
                            self.settings.endpoint,
                            json=payload,
                            headers=headers,
                        )
                    except httpx.TimeoutException as exc:
                        last_error = f"TypeSafe request timed out: {exc.__class__.__name__}"
                        last_status = None
                        break
                    except httpx.HTTPError as exc:
                        last_error = f"TypeSafe transport error: {exc.__class__.__name__}"
                        last_status = None
                        break

                    last_status = response.status_code

                    if response.status_code in RETRY_STATUS_CODES and attempt < self.max_retries:
                        delay = _retry_delay(response, attempt)
                        logger.warning(
                            "TypeSafe %s; retry %s/%s in %.2fs (headers=%s)",
                            response.status_code,
                            attempt + 1,
                            self.max_retries,
                            delay,
                            _redact_headers(response.headers),
                        )
                        self._sleep(delay)
                        continue

                    if response.status_code >= 400:
                        last_error = (
                            f"TypeSafe HTTP {response.status_code}: "
                            f"{_safe_body_snippet(response)}"
                        )
                        break

                    return JevCallResult(
                        ok=True,
                        response=_parse_response(response),
                        latency_ms=_elapsed_ms(started),
                        status_code=response.status_code,
                        attempts=attempts,
                    )
        except JevParseError as exc:
            return JevCallResult(
                ok=False,
                error=str(exc),
                latency_ms=_elapsed_ms(started),
                status_code=last_status,
                attempts=attempts,
            )

        return JevCallResult(
            ok=False,
            error=last_error,
            latency_ms=_elapsed_ms(started),
            status_code=last_status,
            attempts=attempts,
        )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.1, float(retry_after))
        except ValueError:
            pass
    return 0.5 * (2 ** attempt)


def _safe_body_snippet(response: httpx.Response, limit: int = 180) -> str:
    text = (response.text or "").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[:limit] + "..."
    return text or "(empty body)"


def _parse_response(response: httpx.Response) -> JevResponse:
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise JevParseError(f"Invalid JSON from TypeSafe: {exc}") from exc
    except ValueError as exc:
        raise JevParseError(f"Invalid JSON from TypeSafe: {exc}") from exc

    if not isinstance(data, dict):
        raise JevParseError("TypeSafe JSON root must be an object")

    try:
        return JevResponse.model_validate(data)
    except ValidationError as exc:
        raise JevParseError(f"TypeSafe response failed schema validation: {exc}") from exc
