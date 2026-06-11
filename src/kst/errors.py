"""Production error taxonomy for the KST harness.

Every exception raised inside the harness CORE inherits from
:class:`KSTError`. The taxonomy lets the BatteryRunner classify
failures into recoverable (retry, downshift parallelism) versus
fatal (abort run, mark sub-test failed and continue) without string
parsing, and lets the CLI map to deterministic Unix exit codes.

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class KSTError(Exception):
    """Root of the KST error hierarchy.

    All harness-raised exceptions descend from this class so callers
    can install a single broad ``except KSTError`` clause that still
    distinguishes failure classes via :func:`isinstance`.
    """

    def __init__(self, message: str, *, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = dict(context or {})

    def to_dict(self) -> Dict[str, Any]:
        """Structured representation for log emitters and JSON sinks."""
        return {
            "class": type(self).__name__,
            "message": self.message,
            "context": dict(self.context),
        }


class ConfigError(KSTError):
    """Battery configuration is malformed or internally inconsistent.

    Examples: weights that do not sum to 1.0, missing required field,
    a referenced sub-test plugin is not registered.
    """


class PluginContractError(KSTError):
    """A sub-test plugin failed strict signature validation at register-time.

    Carries the offending field name in ``context['field']`` and the
    expected vs actual signature shape in ``context['expected']`` /
    ``context['actual']``.
    """


class AdapterError(KSTError):
    """Transport or response-shape failure inside an adapter.

    Concrete subclasses are :class:`RateLimitError`,
    :class:`TimeoutError` (alias re-exported), and the generic
    AdapterError itself for residual HTTP and parse failures.
    """

    def __init__(
        self,
        message: str,
        *,
        adapter: str = "",
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = dict(context or {})
        if adapter:
            ctx.setdefault("adapter", adapter)
        if status_code is not None:
            ctx.setdefault("status_code", status_code)
        super().__init__(message, context=ctx)
        self.adapter = adapter
        self.status_code = status_code


class RateLimitError(AdapterError):
    """The remote target returned a 429 (or vendor-equivalent) signal.

    ``retry_after_s`` is the seconds-to-wait surfaced by the vendor
    when available; ``None`` means the adapter should fall back to its
    own exponential-backoff schedule.
    """

    def __init__(
        self,
        message: str,
        *,
        adapter: str = "",
        retry_after_s: Optional[float] = None,
        status_code: Optional[int] = 429,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = dict(context or {})
        if retry_after_s is not None:
            ctx.setdefault("retry_after_s", retry_after_s)
        super().__init__(
            message,
            adapter=adapter,
            status_code=status_code,
            context=ctx,
        )
        self.retry_after_s = retry_after_s


class TimeoutError(AdapterError):
    """Adapter call exceeded its budget.

    Note: this shadows the builtin ``TimeoutError`` only inside the
    ``kst.errors`` module namespace. External callers import
    it as ``kst.errors.TimeoutError`` to avoid confusion.
    """


class ScoreValidationError(KSTError):
    """A sub-test produced a score outside its declared range.

    Raised by the harness when ``SubTestScore.score`` exits
    ``[0, max_score]`` or when the sub-test claims a normalized score
    outside ``[0, 100]``. Sub-test plugin authors must catch this in
    development; it is a deterministic data-quality assertion.
    """


class PersistenceError(KSTError):
    """A persistence-layer call failed.

    Wraps psycopg2 / I/O exceptions so the BatteryRunner can decide
    whether to continue with JSONL-only persistence or abort.
    """


class IncompleteBatteryError(KSTError):
    """A scoring aggregation was attempted on a battery that is missing sub-tests.

    Raised by :func:`kst.score.aggregate_score_report` when the
    configured battery declared N sub-tests and fewer than N completed
    successfully. The harness FAILS LOUDLY rather than silently zeroing.
    """

    def __init__(
        self,
        message: str,
        *,
        expected: int,
        actual: int,
        missing: Optional[list] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = dict(context or {})
        ctx.setdefault("expected", expected)
        ctx.setdefault("actual", actual)
        if missing is not None:
            ctx.setdefault("missing", list(missing))
        super().__init__(message, context=ctx)
        self.expected = expected
        self.actual = actual
        self.missing = list(missing or [])


class ResumeError(KSTError):
    """The requested run_id cannot be resumed (not found, terminal, schema mismatch)."""


__all__ = [
    "KSTError",
    "ConfigError",
    "PluginContractError",
    "AdapterError",
    "RateLimitError",
    "TimeoutError",
    "ScoreValidationError",
    "PersistenceError",
    "IncompleteBatteryError",
    "ResumeError",
]
