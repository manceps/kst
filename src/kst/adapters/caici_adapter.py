"""CAI.CI grey-box adapter.

Targets a CAI.CI inference endpoint that emits the canonical
``cognitive_telemetry`` envelope alongside chat-completion text.
The reference CAI.CI service is hosted at chat.cai.ci; operators
configure the exact endpoint via the ``CAICI_ENDPOINT`` environment
variable (or the ``endpoint=`` constructor kwarg). Authentication is
bearer-token based: the token comes from the ``CAICI_API_KEY``
environment variable (or the ``auth_bearer_token=`` constructor
kwarg). No vendor SDK is required; the adapter speaks raw HTTPS via
``requests``.

The adapter captures the full ``cognitive_telemetry`` block emitted
by the inference server and maps it into :class:`GreyBoxTelemetry`
for the sub-test rubrics that score on architectural state.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import requests

from kst.adapters.base import BaseAdapter
from kst.envelope import (
    AdapterCapabilities,
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    GreyBoxTelemetry,
)
from kst.errors import (
    AdapterError,
    ConfigError,
    RateLimitError,
    TimeoutError as KSTTimeoutError,
)

logger = logging.getLogger(__name__)


# Telemetry fields the inference server exposes under
# ``usage.cognitive_telemetry``. The list is the contract between this
# adapter and any sub-test that scores on grey-box signals; new
# top-level keys land here when the inference server adds them.
_TELEMETRY_TOP_LEVEL = (
    "valence",
    "valence_normalized",
    "arousal",
    "seeking_drive",
    "confidence",
    "competence",
    "meta_competence",
    "workspace_selectivity",
    "concordance",
    "autonomy",
    "relatedness",
    "schema_prediction_accuracy",
    "generation_confidence",
    "mean_token_probability",
    "mean_generation_entropy",
    "repetition_ratio",
    "metacognitive_confidence_raw",
    "verified_confidence",
    "epistemic_state",
    "epistemic_confidence",
    "response_utility",
    "persona_boundary_score",
)


# The CAI.CI chat-completions endpoint documents a public capabilities
# envelope under the request-body field ``caici_capabilities``. The
# envelope is an open dictionary; the keys recognised by the server
# (per its OpenAPI schema) are enumerated here. KST validates against
# this allow-list so operator typos do not silently no-op against the
# server.
_CAICI_CAPABILITIES_KEYS = frozenset(
    (
        "research_required",
        "step_c_credibility",
        "research_budget_s",
    )
)


def _parse_caici_capabilities_env(
    raw: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Parse the ``KST_CAICI_CAPABILITIES`` env var into a validated dict.

    Returns ``None`` when the env var is unset or empty (in which case
    the adapter does not add the ``caici_capabilities`` field to the
    request body, preserving default chat-path semantics exactly).

    Raises no exceptions: on malformed JSON, non-dict shape, unknown
    keys, or wrong-type values the function logs a warning and returns
    ``None`` so a typo cannot poison every outbound request.
    """
    if raw is None or raw == "":
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "KST_CAICI_CAPABILITIES is not valid JSON: %s; ignoring.",
            exc,
        )
        return None
    if not isinstance(parsed, dict):
        logger.warning(
            "KST_CAICI_CAPABILITIES must decode to a JSON object; "
            "got %s; ignoring.",
            type(parsed).__name__,
        )
        return None
    unknown = set(parsed.keys()) - _CAICI_CAPABILITIES_KEYS
    if unknown:
        logger.warning(
            "KST_CAICI_CAPABILITIES contains keys not in the public "
            "envelope schema: %s; ignoring entire envelope.",
            sorted(unknown),
        )
        return None
    # Per the public OpenAPI schema:
    #  - research_required: bool
    #  - step_c_credibility: bool
    #  - research_budget_s: number (>= 0)
    validated: Dict[str, Any] = {}
    if "research_required" in parsed:
        v = parsed["research_required"]
        if not isinstance(v, bool):
            logger.warning(
                "KST_CAICI_CAPABILITIES.research_required must be bool; "
                "got %s; ignoring entire envelope.",
                type(v).__name__,
            )
            return None
        validated["research_required"] = v
    if "step_c_credibility" in parsed:
        v = parsed["step_c_credibility"]
        if not isinstance(v, bool):
            logger.warning(
                "KST_CAICI_CAPABILITIES.step_c_credibility must be bool; "
                "got %s; ignoring entire envelope.",
                type(v).__name__,
            )
            return None
        validated["step_c_credibility"] = v
    if "research_budget_s" in parsed:
        v = parsed["research_budget_s"]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            logger.warning(
                "KST_CAICI_CAPABILITIES.research_budget_s must be a "
                "non-negative number; got %s; ignoring entire envelope.",
                type(v).__name__,
            )
            return None
        if v < 0:
            logger.warning(
                "KST_CAICI_CAPABILITIES.research_budget_s must be >= 0; "
                "got %s; ignoring entire envelope.",
                v,
            )
            return None
        validated["research_budget_s"] = float(v)
    return validated if validated else None


def _maybe_float(payload: Dict[str, Any], key: str) -> Optional[float]:
    v = payload.get(key)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _maybe_str(payload: Dict[str, Any], key: str) -> Optional[str]:
    v = payload.get(key)
    if isinstance(v, str):
        return v
    return None


def map_cognitive_telemetry(payload: Dict[str, Any]) -> GreyBoxTelemetry:
    """Map an inference-server ``cognitive_telemetry`` block into :class:`GreyBoxTelemetry`."""
    return GreyBoxTelemetry(
        epistemic_state=_maybe_str(payload, "epistemic_state"),
        confidence=_maybe_float(payload, "confidence"),
        calibration_score=_maybe_float(payload, "verified_confidence"),
        valence=_maybe_float(payload, "valence"),
        arousal=_maybe_float(payload, "arousal"),
        seeking_drive=_maybe_float(payload, "seeking_drive"),
        competence=_maybe_float(payload, "competence"),
        meta_competence=_maybe_float(payload, "meta_competence"),
        workspace_selectivity=_maybe_float(payload, "workspace_selectivity"),
        ags_state=_maybe_str(
            payload.get("adaptive_temperature", {}) or {}, "tier"
        ),
        ags_drift_flag=bool(
            (payload.get("grounding_drift_block", {}) or {}).get("action")
            not in (None, "pass", "")
        )
        if isinstance(payload.get("grounding_drift_block"), dict)
        else None,
        factual_claim_audit=(
            payload.get("factual_claim_audit")
            if isinstance(payload.get("factual_claim_audit"), dict)
            else None
        ),
        tool_routing=(
            payload.get("tool_routing")
            if isinstance(payload.get("tool_routing"), dict)
            else None
        ),
        voice=(
            payload.get("voice")
            if isinstance(payload.get("voice"), dict)
            else None
        ),
        raw=payload,
    )


class CaiciAdapter(BaseAdapter):
    """Adapter for the CAI.CI grey-box chat-completions surface.

    Configuration is environment-variable driven:

    - ``CAICI_ENDPOINT``: the full URL of the CAI.CI chat-completions
      endpoint (e.g. ``https://chat.cai.ci/v1/chat/completions`` or
      ``http://localhost:8082/v1/chat/completions`` for a locally-hosted
      inference server). REQUIRED. If neither the env var nor the
      ``endpoint=`` constructor kwarg is supplied, the constructor
      raises :class:`ConfigError` with a clear message.

    - ``CAICI_API_KEY``: an operator-issued Authorization Bearer token.
      Optional; when absent the adapter sends unauthenticated requests
      (which is fine for a local inference server that does not enforce
      auth). The ``auth_bearer_token=`` constructor kwarg overrides the
      env var.

    The adapter accepts both the OpenAI-compatible chat-completions
    response shape (``{choices: [{message: {content}}], usage:
    {cognitive_telemetry: {...}}}``) and the flattened CAI.CI variant
    (``{response_text, epistemic_state, confidence, ...}``).
    """

    name = "caici"
    capability = AdapterCapability.GREY_BOX

    DEFAULT_MODEL = "caici"
    DEFAULT_RPM = 60

    def __init__(
        self,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 60.0,
        max_attempts: int = 5,
        rpm: Optional[int] = None,
        auth_bearer_token: Optional[str] = None,
    ) -> None:
        resolved_rpm = rpm if rpm is not None else self.DEFAULT_RPM
        super().__init__(
            timeout_s=timeout_s,
            max_attempts=max_attempts,
            rpm=resolved_rpm,
        )
        resolved_endpoint = (
            endpoint
            or os.environ.get("CAICI_ENDPOINT", "")
            or os.environ.get("KST_CAICI_ENDPOINT", "")
        )
        if not resolved_endpoint:
            raise ConfigError(
                "CaiciAdapter requires an endpoint. Set the CAICI_ENDPOINT "
                "environment variable to the full chat-completions URL "
                "(for example https://chat.cai.ci/v1/chat/completions or "
                "http://localhost:8082/v1/chat/completions), or pass "
                "endpoint=... to the constructor.",
                context={"env_var": "CAICI_ENDPOINT"},
            )
        self.endpoint = resolved_endpoint
        self.model = model or self.DEFAULT_MODEL
        # Bearer token: explicit kwarg wins, then CAICI_API_KEY, then the
        # legacy KST_CAICI_BEARER_TOKEN env var for back-compat with
        # tooling that already exports it.
        self.auth_bearer_token: Optional[str] = (
            auth_bearer_token
            or os.environ.get("CAICI_API_KEY")
            or os.environ.get("KST_CAICI_BEARER_TOKEN")
            or None
        )
        # Operator-controllable public capabilities envelope (per the
        # CAI.CI chat-completions OpenAPI schema's ``caici_capabilities``
        # request-body field). When unset / empty / invalid the adapter
        # omits the field and default server-side chat-path semantics
        # are preserved exactly.
        self._caici_capabilities: Optional[Dict[str, Any]] = (
            _parse_caici_capabilities_env(
                os.environ.get("KST_CAICI_CAPABILITIES")
            )
        )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            capability=self.capability,
            rate_limit_rpm=self._rate_limiter._rpm,
            supports_seed=False,
            supports_logprobs=False,
            supports_grey_box_telemetry=True,
            max_tokens=4096,
            default_model_id=self.model,
        )

    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop_sequences:
            body["stop"] = list(request.stop_sequences)
        if self._caici_capabilities is not None:
            # Per the CAI.CI public OpenAPI schema, the chat-completions
            # endpoint accepts an open-dictionary ``caici_capabilities``
            # field on the request body. KST surfaces it through the
            # ``KST_CAICI_CAPABILITIES`` env var so harness operators
            # can flip server-side behaviour (e.g. research bypass)
            # without code changes. A fresh dict each call defends
            # against accidental mutation by downstream observers.
            body["caici_capabilities"] = dict(self._caici_capabilities)

        headers = {"Content-Type": "application/json"}
        if self.auth_bearer_token is not None:
            headers["Authorization"] = f"Bearer {self.auth_bearer_token}"

        # Idempotency-key: the CAI.CI proxy / wake supports an
        # idempotency cache keyed off this header. Reusing the same
        # key across retries of one logical request lets the wake
        # return the cached completion on retry-N instead of
        # re-executing the full chat path (research + decode), which
        # is what turns a retry storm from compounding into
        # constant-cost. The key is derived from
        # ``AdapterRequest.request_id``, which is unique per logical
        # request and stable across retries of that same request.
        headers["X-CAICI-Idempotency-Key"] = f"kst-{request.request_id}"

        try:
            r = requests.post(
                self.endpoint,
                json=body,
                headers=headers,
                timeout=self.timeout_s,
            )
        except requests.Timeout as exc:
            raise KSTTimeoutError(
                f"CAI.CI request timed out after {self.timeout_s:.1f}s",
                adapter=self.name,
                status_code=None,
            ) from exc
        except requests.RequestException as exc:
            raise AdapterError(
                f"CAI.CI transport failure: {exc}",
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
                "CAI.CI rate-limited",
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
                f"CAI.CI HTTP {r.status_code}: {payload}",
                adapter=self.name,
                status_code=r.status_code,
            )

        # The inference server currently returns a flattened envelope of
        # the form ``{response_text, epistemic_state, confidence, ...}``;
        # the OpenAI-compatible variant returns ``{choices: [...],
        # usage: {cognitive_telemetry: {...}}}``. The adapter handles
        # both shapes so a single client works against either variant.
        text = ""
        tele_payload: Dict[str, Any] = {}

        if isinstance(payload.get("choices"), list) and payload["choices"]:
            # OpenAI-compatible shape.
            try:
                text = (
                    payload["choices"][0]["message"].get("content")
                    or ""
                )
            except (KeyError, IndexError, TypeError) as exc:
                raise AdapterError(
                    f"Malformed CAI.CI response: {exc}",
                    adapter=self.name,
                    status_code=r.status_code,
                    context={"payload_keys": list(payload.keys())},
                ) from exc
            usage = payload.get("usage", {}) or {}
            tele_payload = usage.get("cognitive_telemetry", {}) or {}
        elif "response_text" in payload:
            # Flattened shape.
            text = str(payload.get("response_text") or "")
            # Promote every top-level field that is not the response text
            # into the cognitive telemetry payload so the existing mapper
            # can populate the canonical fields.
            tele_payload = {
                k: v for k, v in payload.items() if k != "response_text"
            }
        else:
            raise AdapterError(
                "Malformed CAI.CI response: missing 'choices' and 'response_text'",
                adapter=self.name,
                status_code=r.status_code,
                context={"payload_keys": list(payload.keys())},
            )

        telemetry = (
            map_cognitive_telemetry(tele_payload) if tele_payload else None
        )

        return AdapterResponse(
            request_id=request.request_id,
            text=text,
            model_id=payload.get("model", self.model),
            adapter_name=self.name,
            capability=self.capability,
            status_code=r.status_code,
            raw=payload,
            grey_box_telemetry=telemetry,
        )
