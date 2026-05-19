"""Observability primitives for the KST harness.

Two layers ship in this module:

1. Latency histograms and counters: pure-Python, zero-dependency
   exponential-bucket aggregator that records request latencies per
   adapter and sub-test and emits p50 / p95 / p99 on demand. This is
   the data Grafana scrapes through the Prometheus exposition format
   (:meth:`MetricsRegistry.format_prometheus`).

2. OpenTelemetry trace export hooks: when ``opentelemetry-api`` is
   installed, :class:`OTelTracer` emits spans under the
   ``stt.harness`` instrumentation name; otherwise the calls degrade
   to no-ops without raising. This keeps the harness importable in
   environments that have not yet installed the OTel stack.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import bisect
import contextlib
import logging
import math
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


class LatencyHistogram:
    """Exponential-bucket latency histogram, thread-safe.

    Buckets are powers of two between ``min_s`` and ``max_s``. Each
    record is O(log B) (binary search to find the bucket). Quantile
    estimation linearly interpolates within the bucket containing the
    rank.
    """

    def __init__(
        self,
        *,
        min_s: float = 0.001,
        max_s: float = 60.0,
        steps_per_decade: int = 8,
    ) -> None:
        if min_s <= 0 or max_s <= min_s:
            raise ValueError("min_s must be positive and < max_s.")
        decades = math.log10(max_s / min_s)
        n_buckets = int(math.ceil(decades * steps_per_decade)) + 1
        self._upper_bounds: List[float] = []
        factor = 10.0 ** (1.0 / steps_per_decade)
        v = min_s
        for _ in range(n_buckets):
            self._upper_bounds.append(v)
            v *= factor
        # Sentinel bucket at +inf catches anything above max_s.
        self._upper_bounds.append(float("inf"))
        self._counts: List[int] = [0] * len(self._upper_bounds)
        self._sum_s: float = 0.0
        self._count: int = 0
        self._lock = threading.Lock()

    def record(self, value_s: float) -> None:
        if value_s < 0 or math.isnan(value_s):
            return
        with self._lock:
            idx = bisect.bisect_left(self._upper_bounds, value_s)
            if idx >= len(self._upper_bounds):
                idx = len(self._upper_bounds) - 1
            self._counts[idx] += 1
            self._sum_s += value_s
            self._count += 1

    def quantile(self, q: float) -> Optional[float]:
        if not 0.0 < q < 1.0:
            raise ValueError("q must lie in (0, 1).")
        with self._lock:
            if self._count == 0:
                return None
            target = q * self._count
            cumulative = 0
            for i, c in enumerate(self._counts):
                cumulative += c
                if cumulative >= target:
                    # Linear within-bucket interpolation.
                    lower = self._upper_bounds[i - 1] if i > 0 else 0.0
                    upper = self._upper_bounds[i]
                    if math.isinf(upper):
                        return lower
                    if c == 0:
                        return upper
                    in_bucket_position = (
                        (cumulative - target) / float(c)
                    )
                    return float(upper - in_bucket_position * (upper - lower))
            return self._upper_bounds[-2]

    def count(self) -> int:
        with self._lock:
            return self._count

    def mean(self) -> Optional[float]:
        with self._lock:
            if self._count == 0:
                return None
            return self._sum_s / float(self._count)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "count": self.count(),
            "mean_s": self.mean(),
            "p50_s": self.quantile(0.50),
            "p95_s": self.quantile(0.95),
            "p99_s": self.quantile(0.99),
        }


class Counter:
    """Atomic counter, thread-safe."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def inc(self, n: int = 1) -> None:
        with self._lock:
            self._value += n

    def get(self) -> int:
        with self._lock:
            return self._value


class MetricsRegistry:
    """Per-process registry for adapter latencies and score distributions.

    Counters and histograms are keyed by a label tuple so callers can
    aggregate across adapter / sub-test cleanly.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._adapter_latency: Dict[str, LatencyHistogram] = {}
        self._sub_test_latency: Dict[str, LatencyHistogram] = {}
        self._sub_test_scores: Dict[str, List[float]] = {}
        self._counters: Dict[str, Counter] = {}

    # ── Counters ─────────────────────────────────────────────────────

    def counter(self, name: str) -> Counter:
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                c = Counter()
                self._counters[name] = c
            return c

    # ── Latency ──────────────────────────────────────────────────────

    def adapter_latency(self, adapter: str) -> LatencyHistogram:
        with self._lock:
            h = self._adapter_latency.get(adapter)
            if h is None:
                h = LatencyHistogram()
                self._adapter_latency[adapter] = h
            return h

    def sub_test_latency(self, construct_id: str) -> LatencyHistogram:
        with self._lock:
            h = self._sub_test_latency.get(construct_id)
            if h is None:
                h = LatencyHistogram()
                self._sub_test_latency[construct_id] = h
            return h

    def record_score(self, construct_id: str, normalized: float) -> None:
        with self._lock:
            self._sub_test_scores.setdefault(construct_id, []).append(
                float(normalized)
            )

    # ── Snapshot ─────────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": {k: c.get() for k, c in self._counters.items()},
                "adapter_latency": {
                    k: h.snapshot() for k, h in self._adapter_latency.items()
                },
                "sub_test_latency": {
                    k: h.snapshot() for k, h in self._sub_test_latency.items()
                },
                "sub_test_scores": {
                    k: {
                        "n": len(v),
                        "mean": (sum(v) / len(v)) if v else None,
                        "min": min(v) if v else None,
                        "max": max(v) if v else None,
                    }
                    for k, v in self._sub_test_scores.items()
                },
            }

    # ── Prometheus exposition ────────────────────────────────────────

    def format_prometheus(self) -> str:
        """Render the registry in Prometheus text-exposition format."""
        lines: List[str] = []
        for name, c in sorted(self._counters.items()):
            safe = _prometheus_metric_name(f"stt_{name}_total")
            lines.append(f"# TYPE {safe} counter")
            lines.append(f"{safe} {c.get()}")
        for adapter, h in sorted(self._adapter_latency.items()):
            base = _prometheus_metric_name(f"stt_adapter_latency_seconds")
            label = _prometheus_label_value(adapter)
            snap = h.snapshot()
            lines.append(f"# TYPE {base} summary")
            for q, val in (
                (0.5, snap["p50_s"]),
                (0.95, snap["p95_s"]),
                (0.99, snap["p99_s"]),
            ):
                if val is None:
                    continue
                lines.append(
                    f"{base}{{adapter=\"{label}\",quantile=\"{q}\"}} {val}"
                )
            lines.append(
                f"{base}_count{{adapter=\"{label}\"}} {snap['count']}"
            )
            if snap["mean_s"] is not None:
                lines.append(
                    f"{base}_sum{{adapter=\"{label}\"}} "
                    f"{snap['mean_s'] * snap['count']}"
                )
        return "\n".join(lines) + "\n"


def _prometheus_metric_name(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


def _prometheus_label_value(v: str) -> str:
    return v.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ")


# ──────────────────────────────────────────────────────────────────────
# OpenTelemetry export (optional dependency).
# ──────────────────────────────────────────────────────────────────────


class OTelTracer:
    """Thin wrapper around the OpenTelemetry tracer API.

    Becomes a no-op when ``opentelemetry-api`` is not installed.
    Callers use it via the :meth:`span` context manager so the
    no-op path never raises.
    """

    INSTRUMENTATION_NAME = "stt.harness"

    def __init__(self, *, instrumentation_name: Optional[str] = None) -> None:
        self._tracer: Any = None
        name = instrumentation_name or self.INSTRUMENTATION_NAME
        try:
            from opentelemetry import trace  # type: ignore

            self._tracer = trace.get_tracer(name)
            self.enabled = True
        except ImportError:
            self.enabled = False
        except Exception as exc:  # noqa: BLE001
            logger.debug("OTel tracer disabled: %s", exc)
            self.enabled = False

    @contextlib.contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        if not self.enabled or self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:  # noqa: BLE001
                        # OTel SDK rejects unsupported types; coerce to str.
                        span.set_attribute(k, str(v))
            yield span


# Module-level registry: production callers usually want one, but
# tests construct their own to keep isolation.
default_registry = MetricsRegistry()
default_tracer = OTelTracer()


__all__ = [
    "Counter",
    "LatencyHistogram",
    "MetricsRegistry",
    "OTelTracer",
    "default_registry",
    "default_tracer",
]
