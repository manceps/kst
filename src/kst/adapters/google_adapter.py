"""Google Gemini adapter (generativelanguage.googleapis.com).

Black-box adapter. Reads ``GOOGLE_API_KEY`` from the environment by
default. Targets the v1beta REST surface so no Google SDK is
required. Retry, rate-limit, and timeout semantics are inherited
from :class:`BaseAdapter`.

Author: Al Kari, Manceps Inc., research@manceps.com.
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
        thinking_budget: Optional[int] = None,
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
        # Thinking-only Gemini variants (e.g. gemini-3.x-pro-preview) refuse
        # thinkingBudget=0 and silently consume the maxOutputTokens cap as
        # hidden reasoning. We default to 1024 thinking tokens, expand the
        # output envelope by that amount so the plugin's requested visible
        # budget is preserved, and let the operator override via
        # KST_GOOGLE_THINKING_BUDGET.
        if thinking_budget is None:
            try:
                thinking_budget = int(os.environ.get("KST_GOOGLE_THINKING_BUDGET", "1024"))
            except ValueError:
                thinking_budget = 1024
        self.thinking_budget = int(thinking_budget)

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
        # Expand the output envelope so the plugin's intended visible-token
        # budget survives Gemini's hidden chain-of-thought. For non-thinking
        # models the extra headroom is harmless: the model stops at STOP.
        total_output_tokens = int(request.max_tokens) + max(0, self.thinking_budget)
        gen_cfg: Dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": total_output_tokens,
        }
        # Send `thinkingConfig` whenever the operator set a non-negative
        # budget, including 0. Some Gemini variants (notably
        # gemini-3.5-flash) default to thinking-on when this field is
        # omitted entirely, silently consuming the visible-token budget
        # on hidden reasoning. Sending `thinkingBudget=0` explicitly is
        # the documented opt-out path. A negative budget (e.g. via a
        # defensive clamp or an operator-supplied invalid value) is
        # treated as "do not touch thinkingConfig".
        if self.thinking_budget >= 0:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen_cfg,
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
