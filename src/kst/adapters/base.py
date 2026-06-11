"""Abstract adapter protocol, capabilities, and shared base.

Concrete adapters in this package follow :class:`AdapterProtocol`
(PEP 544 structural subtype). :class:`BaseAdapter` is a production
ABC that handles the boilerplate uniformly: timing, structured-error
capture, exponential backoff with jitter, rate-limit-aware retry, and
deterministic timeout enforcement. Concrete adapters override
:meth:`_send` (vendor-specific transport) and optionally
:meth:`_classify_response` (HTTP-status to exception mapping).

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import abc
import logging
import random
import threading
import time
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from kst.envelope import (
    AdapterCapabilities,
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    TargetRequest,
    TargetResponse,
)
from kst.errors import (
    AdapterError,
    RateLimitError,
    TimeoutError as KSTTimeoutError,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class AdapterProtocol(Protocol):
    """Structural-typed contract every KST adapter must satisfy."""

    name: str
    capability: AdapterCapability

    def get_capabilities(self) -> AdapterCapabilities:  # pragma: no cover - protocol
        ...

    def send(
        self, request: TargetRequest
    ) -> TargetResponse:  # pragma: no cover - protocol
        ...

    def run_multi_turn_dispatch(
        self, prompts: Sequence[str]
    ) -> List[str]:  # pragma: no cover - protocol
        ...

    def close(self) -> None:  # pragma: no cover - protocol
        ...


class _RateLimiter:
    """Token-bucket rate limiter used by every BaseAdapter instance.

    ``rpm`` (requests per minute) is the only dimension enforced here.
    A ``None`` rpm disables limiting. Thread-safe; backs off in-place
    on the calling thread when the bucket is empty.
    """

    def __init__(self, rpm: Optional[int]) -> None:
        self._rpm = rpm
        self._lock = threading.Lock()
        self._next_allowed: float = 0.0

    def acquire(self) -> None:
        if self._rpm is None or self._rpm <= 0:
            return
        gap = 60.0 / float(self._rpm)
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + gap


class BaseAdapter(abc.ABC):
    """Production base that times calls, retries with backoff, and captures errors.

    Subclass contract:

    - Set the class attributes ``name`` and ``capability``.
    - Implement :meth:`_send_once`. It MUST raise:
      :class:`kst.errors.RateLimitError` on 429-class signals
      (so retry kicks in), :class:`KSTTimeoutError` on transport
      timeouts, :class:`AdapterError` on residual HTTP failures, and
      MUST return a populated :class:`AdapterResponse` on success.
    - Optionally override :meth:`get_capabilities` to declare
      adapter-specific knobs (seed support, logprobs, etc.).
    """

    name: str = "base"
    capability: AdapterCapability = AdapterCapability.BLACK_BOX

    DEFAULT_TIMEOUT_S: float = 60.0
    DEFAULT_MAX_ATTEMPTS: int = 5
    DEFAULT_BACKOFF_BASE_S: float = 1.0
    DEFAULT_BACKOFF_MAX_S: float = 30.0
    DEFAULT_RPM: Optional[int] = None

    def __init__(
        self,
        *,
        timeout_s: Optional[float] = None,
        max_attempts: Optional[int] = None,
        backoff_base_s: Optional[float] = None,
        backoff_max_s: Optional[float] = None,
        rpm: Optional[int] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.timeout_s = timeout_s if timeout_s is not None else self.DEFAULT_TIMEOUT_S
        self.max_attempts = (
            max_attempts if max_attempts is not None else self.DEFAULT_MAX_ATTEMPTS
        )
        self.backoff_base_s = (
            backoff_base_s if backoff_base_s is not None else self.DEFAULT_BACKOFF_BASE_S
        )
        self.backoff_max_s = (
            backoff_max_s if backoff_max_s is not None else self.DEFAULT_BACKOFF_MAX_S
        )
        resolved_rpm = rpm if rpm is not None else self.DEFAULT_RPM
        self._rate_limiter = _RateLimiter(resolved_rpm)
        self._rng = rng or random.Random()

    # ── Public API ────────────────────────────────────────────────────

    def get_capabilities(self) -> AdapterCapabilities:
        """Default capability declaration; subclasses override with vendor specifics."""
        return AdapterCapabilities(
            name=self.name,
            capability=self.capability,
            rate_limit_rpm=getattr(self, "_declared_rpm", None),
            supports_seed=False,
            supports_logprobs=False,
            supports_grey_box_telemetry=(
                self.capability == AdapterCapability.GREY_BOX
            ),
            max_tokens=4096,
            default_model_id=getattr(self, "model", "") or "",
        )

    def send_adapter(self, request: AdapterRequest) -> AdapterResponse:
        """Adapter-tier entrypoint that consumes the production AdapterRequest."""
        attempts = 0
        last_exc: Optional[BaseException] = None
        start = time.monotonic()

        while attempts < self.max_attempts:
            attempts += 1
            self._rate_limiter.acquire()
            attempt_start = time.monotonic()
            try:
                response = self._send_once(request)
                response.attempts = attempts
                response.latency_s = time.monotonic() - start
                return response
            except RateLimitError as exc:
                last_exc = exc
                wait = self._compute_rate_limit_backoff(exc, attempts)
                logger.warning(
                    "adapter=%s rate_limited attempt=%d/%d wait=%.2fs status=%s",
                    self.name, attempts, self.max_attempts, wait, exc.status_code,
                )
                if attempts >= self.max_attempts:
                    break
                time.sleep(wait)
                continue
            except KSTTimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "adapter=%s timeout attempt=%d/%d after %.2fs",
                    self.name, attempts, self.max_attempts,
                    time.monotonic() - attempt_start,
                )
                if attempts >= self.max_attempts:
                    break
                time.sleep(self._compute_backoff(attempts))
                continue
            except AdapterError as exc:
                last_exc = exc
                # 5xx is retryable; 4xx (other than 429) is fatal.
                status = exc.status_code or 0
                retryable = status == 0 or 500 <= status < 600
                logger.warning(
                    "adapter=%s adapter_error attempt=%d/%d status=%s retryable=%s msg=%s",
                    self.name, attempts, self.max_attempts, status, retryable, exc.message,
                )
                if not retryable or attempts >= self.max_attempts:
                    break
                time.sleep(self._compute_backoff(attempts))
                continue
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.exception(
                    "adapter=%s unhandled exception attempt=%d/%d",
                    self.name, attempts, self.max_attempts,
                )
                if attempts >= self.max_attempts:
                    break
                time.sleep(self._compute_backoff(attempts))

        # All retries exhausted.
        latency = time.monotonic() - start
        message = str(last_exc) if last_exc is not None else "unknown adapter failure"
        status_code = getattr(last_exc, "status_code", None) if last_exc is not None else None
        if status_code is None:
            status_code = 599
        return AdapterResponse(
            request_id=request.request_id,
            text="",
            model_id="unknown",
            adapter_name=self.name,
            capability=self.capability,
            status_code=int(status_code),
            latency_s=latency,
            attempts=attempts,
            error=f"{type(last_exc).__name__ if last_exc else 'AdapterError'}: {message}",
        )

    def send(self, request: TargetRequest) -> TargetResponse:
        """Back-compat path: accept the legacy request, return the legacy response.

        Routes through :meth:`send_adapter` so the retry / rate-limit
        / timeout semantics apply uniformly even to legacy callers.
        """
        adapter_req = AdapterRequest.from_target_request(request)
        adapter_resp = self.send_adapter(adapter_req)
        return TargetResponse(
            request_id=adapter_resp.request_id,
            text=adapter_resp.text,
            model_id=adapter_resp.model_id,
            adapter_name=adapter_resp.adapter_name,
            capability=adapter_resp.capability,
            status_code=adapter_resp.status_code,
            latency_s=adapter_resp.latency_s,
            structured=dict(adapter_resp.structured),
            telemetry=adapter_resp.grey_box_telemetry,
            error=adapter_resp.error,
            raw=adapter_resp.raw,
        )

    def close(self) -> None:
        """Default no-op; override when the adapter holds resources."""
        return None

    def run_multi_turn_dispatch(
        self,
        prompts: Sequence[str],
        *,
        system: Optional[str] = None,
        construct_id: str = "",
        item_id: str = "",
        sub_test_version: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: Optional[int] = None,
    ) -> List[str]:
        """Dispatch a sequence of prompts as a multi-turn conversation.

        The default implementation chains the prompts sequentially: each
        turn is sent as its own request with the prior turns concatenated
        into the new prompt as conversation context. Adapters with a
        native multi-turn API (e.g. CAI.CI's session-bearing chat path)
        should override this method to preserve the session across turns
        rather than concatenate.

        DDR is the primary in-tree consumer: its three-turn protocol
        (Phase 1 strategy commitment, Phase 2 insufficiency injection,
        Phase 3 considered response) calls this method once per item.
        Returns the response text for each turn in order.
        """
        if not prompts:
            return []
        responses: List[str] = []
        history: List[tuple[str, str]] = []
        for turn_idx, prompt_text in enumerate(prompts):
            if history:
                context_blocks = []
                for prior_prompt, prior_response in history:
                    context_blocks.append(f"[turn]\nuser:\n{prior_prompt}")
                    context_blocks.append(f"assistant:\n{prior_response}")
                context_blocks.append(f"[turn]\nuser:\n{prompt_text}")
                full_prompt = "\n\n".join(context_blocks)
            else:
                full_prompt = prompt_text
            request = AdapterRequest(
                prompt=full_prompt,
                system=system,
                construct_id=construct_id,
                item_id=f"{item_id}::turn{turn_idx + 1}" if item_id else "",
                sub_test_version=sub_test_version,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            )
            response = self.send_adapter(request)
            text = response.text or ""
            responses.append(text)
            history.append((prompt_text, text))
        return responses

    # ── Subclass hooks ────────────────────────────────────────────────

    @abc.abstractmethod
    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        """One attempt of the wire call.

        MUST raise :class:`RateLimitError`, :class:`KSTTimeoutError`,
        or :class:`AdapterError` on failure. MUST return a populated
        :class:`AdapterResponse` on success.
        """

    # ── Backoff math (overridable, public for unit tests) ────────────

    def _compute_backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped at ``backoff_max_s``.

        attempt is 1-indexed (the first failure passes 1).
        """
        cap = self.backoff_max_s
        upper = min(cap, self.backoff_base_s * (2 ** (max(attempt, 1) - 1)))
        return self._rng.uniform(0.0, upper)

    def _compute_rate_limit_backoff(
        self, exc: RateLimitError, attempt: int
    ) -> float:
        """Honour the vendor's Retry-After if any, otherwise fall back to backoff.

        When the vendor supplies a ``Retry-After`` header the adapter
        sleeps for exactly that duration (capped at ``backoff_max_s``).

        When it does not, the floor of the wait is one full rate-window
        per retry attempt: ``60.0 / rpm * attempt`` seconds. The
        intuition: if a 429 fires and the adapter retries inside the
        same 60s rate-window that the original request consumed,
        retry-N lands in the SAME budget bucket as retry-N-1 and the
        backend re-rejects, reinforcing the rate-limit storm. Sleeping
        for at least one full window per attempt guarantees retry-N
        lands in retry-N's own fresh budget window.

        The ``backoff_max_s`` cap still applies as the upper bound so
        the jittered exponential backoff path is preserved when it is
        already large enough.
        """
        if exc.retry_after_s is not None and exc.retry_after_s >= 0.0:
            return min(self.backoff_max_s, float(exc.retry_after_s))
        jittered = self._compute_backoff(attempt)
        rpm = getattr(self._rate_limiter, "_rpm", None)
        if rpm is None or rpm <= 0:
            return jittered
        window_floor = (60.0 / float(rpm)) * max(attempt, 1)
        return max(jittered, window_floor)
