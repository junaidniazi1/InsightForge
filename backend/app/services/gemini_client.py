"""Gemini client wrapper.

Design rules:
  - The Google SDK is imported *lazily* inside _client_or_raise() so missing-key
    deployments don't crash on module import. The whole AI surface returns a
    typed AIUnavailable that the router turns into a 503.
  - Exponential backoff on 429 / 503 / transient network errors before giving
    up — Gemini's free tier rate-limits aggressively.
  - generate_json uses structured-output (response_mime_type = application/json
    + response_schema) for machine-readable results.
  - The whole class is injectable: services accept a `GeminiClient` parameter,
    and tests pass a stub.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from ..config import Settings

log = logging.getLogger(__name__)


class AIUnavailable(RuntimeError):
    """Raised when AI generation can't proceed (missing key / rate-limited / SDK error)."""

    def __init__(self, message: str, *, status_hint: int = 503) -> None:
        super().__init__(message)
        self.status_hint = status_hint


# Transient HTTP status codes we'll back off on.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_BACKOFFS_SECONDS = (1.0, 2.0, 4.0)


@dataclass
class _GeminiResponse:
    text: str


class GeminiClient:
    """Thin wrapper around `google.genai`.

    Public surface intentionally tiny:
      - generate_text(system, prompt) -> str
      - generate_json(system, prompt, schema) -> dict[str, Any]
    """

    def __init__(
        self,
        settings: Settings,
        *,
        backoffs: tuple[float, ...] = _DEFAULT_BACKOFFS_SECONDS,
    ) -> None:
        self.settings = settings
        self._backoffs = backoffs
        self._client: Any | None = None  # cached SDK client

    # -- internal --------------------------------------------------------

    def _client_or_raise(self) -> Any:
        if not self.settings.gemini_api_key:
            raise AIUnavailable("GEMINI_API_KEY is not configured on the backend.")
        if self._client is None:
            try:
                from google import genai  # type: ignore  # lazy import
            except ImportError as exc:  # pragma: no cover - install-time only
                raise AIUnavailable(f"google-genai SDK not installed: {exc}") from exc
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _retryable(self, exc: BaseException) -> bool:
        # The SDK raises google.genai.errors.APIError with a `code` attribute.
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if isinstance(code, int) and code in _RETRYABLE_STATUS:
            return True
        # Bare timeouts / connection errors from httpx.
        name = type(exc).__name__.lower()
        return "timeout" in name or "connection" in name

    def _call_with_backoff(self, fn, *args, **kwargs) -> Any:
        last_exc: BaseException | None = None
        for attempt, delay in enumerate((*self._backoffs, None)):  # one final no-sleep attempt
            try:
                return fn(*args, **kwargs)
            except AIUnavailable:
                raise
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                if not self._retryable(exc):
                    log.warning("Gemini call failed non-retryably: %s", exc)
                    raise AIUnavailable(f"AI request failed: {exc}") from exc
                log.info("Gemini call retryable error (attempt %d): %s", attempt, exc)
                if delay is None:
                    break
                time.sleep(delay)
        assert last_exc is not None  # for type-checkers
        raise AIUnavailable(
            "AI temporarily unavailable (rate-limited or transient error). "
            "Try again in a few seconds."
        ) from last_exc

    # -- public ----------------------------------------------------------

    def generate_text(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.5,
    ) -> str:
        """Free-form text generation. Returns the model's text response."""
        client = self._client_or_raise()
        from google.genai import types as gtypes  # type: ignore

        def _do() -> str:
            resp = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                ),
            )
            text = getattr(resp, "text", None) or ""
            if not text:
                raise AIUnavailable("Gemini returned an empty response.")
            return text

        return self._call_with_backoff(_do)

    def generate_json(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Structured-output generation. Parses the JSON response into a dict.

        The schema is sent to Gemini as `response_schema`, which constrains
        decoding to that shape. We still json.loads(...) defensively.
        """
        client = self._client_or_raise()
        from google.genai import types as gtypes  # type: ignore

        def _do() -> dict[str, Any]:
            resp = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )
            text = getattr(resp, "text", None) or ""
            if not text:
                raise AIUnavailable("Gemini returned an empty response.")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AIUnavailable(f"Gemini returned non-JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                # Some schemas naturally yield arrays — wrap them so callers
                # always see a dict.
                return {"items": parsed}
            return parsed

        return self._call_with_backoff(_do)


__all__ = ["GeminiClient", "AIUnavailable", "_GeminiResponse"]
