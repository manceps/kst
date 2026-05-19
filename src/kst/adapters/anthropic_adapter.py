"""Adapter for the Messages API of the closed-API vendor at api.anthropic.com.

Black-box adapter. The vendor's SDK is intentionally not imported;
the adapter speaks raw HTTPS via ``requests`` so the harness has no
SDK version coupling. Retry, rate-limit, and timeout semantics are
inherited from :class:`BaseAdapter`.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

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


class AnthropicAdapter(BaseAdapter):
    """Adapter for the closed-API vendor's ``/v1/messages`` endpoint."""

    name = "anthropic_messages"
    capability = AdapterCapability.BLACK_BOX

    DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
    DEFAULT_VERSION = "2023-06-01"
    # Pinned at adapter-author time (2026-05-16). Override via kwarg or env.
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout_s: float = 60.0,
        max_attempts: int = 5,
        rpm: Optional[int] = None,
        api_version: Optional[str] = None,
    ) -> None:
        super().__init__(
            timeout_s=timeout_s,
            max_attempts=max_attempts,
            rpm=rpm,
        )
        self.model = (
            model
            or os.environ.get("KST_ANTHROPIC_MODEL", "")
            or self.DEFAULT_MODEL
        )
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.api_version = api_version or self.DEFAULT_VERSION

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            capability=self.capability,
            rate_limit_rpm=self._rate_limiter._rpm,
            supports_seed=False,
            supports_logprobs=False,
            supports_grey_box_telemetry=False,
            max_tokens=8192,
            default_model_id=self.model,
        )

    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        if not self.api_key:
            raise AdapterError(
                "ANTHROPIC_API_KEY not configured.",
                adapter=self.name,
                status_code=401,
            )
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": "user", "content": request.prompt},
            ],
        }
        if request.system:
            body["system"] = request.system
        if request.stop_sequences:
            body["stop_sequences"] = list(request.stop_sequences)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(
                self.endpoint, json=body, headers=headers, timeout=self.timeout_s
            )
        except requests.Timeout as exc:
            raise KSTTimeoutError(
                f"Vendor request timed out after {self.timeout_s:.1f}s",
                adapter=self.name,
                status_code=None,
            ) from exc
        except requests.RequestException as exc:
            raise AdapterError(
                f"Vendor transport failure: {exc}",
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
                "Vendor rate-limited",
                adapter=self.name,
                retry_after_s=retry_after,
                status_code=429,
            )

        try:
            payload: Dict[str, Any] = r.json()
        except ValueError:
            payload = {"raw_text": r.text}

        if r.status_code != 200:
            raise AdapterError(
                f"Vendor HTTP {r.status_code}: {payload}",
                adapter=self.name,
                status_code=r.status_code,
            )

        text = ""
        parts: List[Dict[str, Any]] = payload.get("content", []) or []
        if not isinstance(parts, list):
            raise AdapterError(
                "Malformed vendor response: 'content' is not a list.",
                adapter=self.name,
                status_code=r.status_code,
            )
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text", "")

        return AdapterResponse(
            request_id=request.request_id,
            text=text,
            model_id=payload.get("model", self.model),
            adapter_name=self.name,
            capability=self.capability,
            status_code=r.status_code,
            raw=payload,
            rate_limit_observed={
                "anthropic-ratelimit-requests-remaining":
                    r.headers.get("anthropic-ratelimit-requests-remaining"),
                "anthropic-ratelimit-tokens-remaining":
                    r.headers.get("anthropic-ratelimit-tokens-remaining"),
            },
        )
