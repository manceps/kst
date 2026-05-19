"""OpenAI Chat Completions adapter.

Black-box adapter. Reads the API key from ``OPENAI_API_KEY`` by
default (constructor injection supported for tests). Targets
``/v1/chat/completions`` directly via ``requests`` so the adapter
stays SDK-version agnostic. Retry, rate-limit, and timeout semantics
are inherited from :class:`BaseAdapter`.

The default model id is pinned to the latest production-grade Chat
Completions model at adapter-author time. Operators override via the
``model=`` kwarg or the ``KST_OPENAI_MODEL`` env var.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

from kst.adapters.base import BaseAdapter
from kst.envelope import (
    AdapterCapabilities,
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
)
from kst.errors import (
    AdapterError,
    RateLimitError,
    TimeoutError as KSTTimeoutError,
)


class OpenAIAdapter(BaseAdapter):
    """Adapter for the OpenAI ``/v1/chat/completions`` endpoint."""

    name = "openai"
    capability = AdapterCapability.BLACK_BOX

    DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
    # Pinned at adapter-author time (2026-05-16). Override via kwarg or env.
    DEFAULT_MODEL = "gpt-4o-2024-11-20"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout_s: float = 60.0,
        max_attempts: int = 5,
        rpm: Optional[int] = None,
    ) -> None:
        super().__init__(
            timeout_s=timeout_s,
            max_attempts=max_attempts,
            rpm=rpm,
        )
        self.model = (
            model or os.environ.get("KST_OPENAI_MODEL", "") or self.DEFAULT_MODEL
        )
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            capability=self.capability,
            rate_limit_rpm=self._rate_limiter._rpm,
            supports_seed=True,
            supports_logprobs=True,
            supports_grey_box_telemetry=False,
            max_tokens=16384,
            default_model_id=self.model,
        )

    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        if not self.api_key:
            raise AdapterError(
                "OPENAI_API_KEY not configured.",
                adapter=self.name,
                status_code=401,
            )
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.seed is not None:
            body["seed"] = int(request.seed)
        if request.stop_sequences:
            body["stop"] = list(request.stop_sequences)
        if request.request_logprobs:
            body["logprobs"] = True

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(
                self.endpoint, json=body, headers=headers, timeout=self.timeout_s
            )
        except requests.Timeout as exc:
            raise KSTTimeoutError(
                f"OpenAI request timed out after {self.timeout_s:.1f}s",
                adapter=self.name,
                status_code=None,
            ) from exc
        except requests.RequestException as exc:
            raise AdapterError(
                f"OpenAI transport failure: {exc}",
                adapter=self.name,
                status_code=None,
            ) from exc

        if r.status_code == 429:
            retry_after = None
            try:
                retry_after = float(r.headers.get("retry-after", "") or "")
            except ValueError:
                retry_after = None
            raise RateLimitError(
                "OpenAI rate-limited",
                adapter=self.name,
                retry_after_s=retry_after,
                status_code=429,
                context={"x-ratelimit-remaining-requests":
                         r.headers.get("x-ratelimit-remaining-requests")},
            )

        try:
            payload: Dict[str, Any] = r.json()
        except ValueError:
            payload = {"raw_text": r.text}

        if r.status_code != 200:
            raise AdapterError(
                f"OpenAI HTTP {r.status_code}: {payload}",
                adapter=self.name,
                status_code=r.status_code,
            )

        text = ""
        logprobs = None
        try:
            choice = payload["choices"][0]
            text = choice["message"].get("content") or ""
            logprobs = choice.get("logprobs")
        except (KeyError, IndexError, TypeError) as exc:
            raise AdapterError(
                f"Malformed OpenAI response: {exc}",
                adapter=self.name,
                status_code=r.status_code,
                context={"payload_keys": list(payload.keys())},
            ) from exc

        return AdapterResponse(
            request_id=request.request_id,
            text=text,
            model_id=payload.get("model", self.model),
            adapter_name=self.name,
            capability=self.capability,
            status_code=r.status_code,
            raw=payload,
            logprobs=logprobs,
            rate_limit_observed={
                "x-ratelimit-remaining-requests":
                    r.headers.get("x-ratelimit-remaining-requests"),
                "x-ratelimit-remaining-tokens":
                    r.headers.get("x-ratelimit-remaining-tokens"),
            },
        )
