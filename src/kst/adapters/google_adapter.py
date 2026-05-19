"""Google Gemini adapter (generativelanguage.googleapis.com).

Black-box adapter. Reads ``GOOGLE_API_KEY`` from the environment by
default. Targets the v1beta REST surface so no Google SDK is
required. Retry, rate-limit, and timeout semantics are inherited
from :class:`BaseAdapter`.

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


class GoogleAdapter(BaseAdapter):
    """Adapter for Gemini's ``v1beta/models/<model>:generateContent`` endpoint."""

    name = "google_gemini"
    capability = AdapterCapability.BLACK_BOX

    DEFAULT_HOST = "https://generativelanguage.googleapis.com"
    # Pinned at adapter-author time (2026-05-16). Override via kwarg or env.
    DEFAULT_MODEL = "gemini-1.5-pro-002"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
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
            model or os.environ.get("KST_GOOGLE_MODEL", "") or self.DEFAULT_MODEL
        )
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self.host = host or self.DEFAULT_HOST

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

    def _endpoint(self) -> str:
        return (
            f"{self.host}/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        if not self.api_key:
            raise AdapterError(
                "GOOGLE_API_KEY not configured.",
                adapter=self.name,
                status_code=401,
            )
        parts = [{"text": request.prompt}]
        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.stop_sequences:
            body["generationConfig"]["stopSequences"] = list(request.stop_sequences)
        if request.system:
            body["systemInstruction"] = {
                "role": "system",
                "parts": [{"text": request.system}],
            }

        try:
            r = requests.post(
                self._endpoint(),
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout_s,
            )
        except requests.Timeout as exc:
            raise KSTTimeoutError(
                f"Gemini request timed out after {self.timeout_s:.1f}s",
                adapter=self.name,
                status_code=None,
            ) from exc
        except requests.RequestException as exc:
            raise AdapterError(
                f"Gemini transport failure: {exc}",
                adapter=self.name,
                status_code=None,
            ) from exc

        if r.status_code in (429,):
            retry_after = None
            try:
                retry_after = float(r.headers.get("retry-after", "") or "")
            except ValueError:
                retry_after = None
            raise RateLimitError(
                "Gemini rate-limited",
                adapter=self.name,
                retry_after_s=retry_after,
                status_code=r.status_code,
            )

        try:
            payload: Dict[str, Any] = r.json()
        except ValueError:
            payload = {"raw_text": r.text}

        if r.status_code != 200:
            # Gemini surfaces RESOURCE_EXHAUSTED inside the body too.
            err = (payload or {}).get("error", {})
            if isinstance(err, dict) and err.get("status") == "RESOURCE_EXHAUSTED":
                raise RateLimitError(
                    f"Gemini RESOURCE_EXHAUSTED: {err.get('message', '')}",
                    adapter=self.name,
                    status_code=r.status_code,
                )
            raise AdapterError(
                f"Gemini HTTP {r.status_code}: {payload}",
                adapter=self.name,
                status_code=r.status_code,
            )

        text = ""
        candidates: List[Dict[str, Any]] = payload.get("candidates", []) or []
        if candidates:
            cand_parts = candidates[0].get("content", {}).get("parts", []) or []
            for p in cand_parts:
                if isinstance(p, dict) and "text" in p:
                    text += p["text"]

        return AdapterResponse(
            request_id=request.request_id,
            text=text,
            model_id=self.model,
            adapter_name=self.name,
            capability=self.capability,
            status_code=r.status_code,
            raw=payload,
        )
