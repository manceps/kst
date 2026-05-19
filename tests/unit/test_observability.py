"""Unit tests for kst.observability.

Cover LatencyHistogram quantile interpolation, MetricsRegistry
snapshot, Prometheus exposition shape, and OTelTracer no-op when
opentelemetry is absent.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import pytest

from kst.observability import (
    Counter,
    LatencyHistogram,
    MetricsRegistry,
    OTelTracer,
)


def test_counter_increments():
    c = Counter()
    assert c.get() == 0
    c.inc()
    c.inc(5)
    assert c.get() == 6


def test_latency_histogram_quantiles():
    h = LatencyHistogram(min_s=0.001, max_s=10.0)
    for v in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        h.record(v)
    p50 = h.quantile(0.5)
    p95 = h.quantile(0.95)
    assert 0.3 <= p50 <= 0.7
    assert 0.9 <= p95 <= 1.5
    assert h.count() == 10
    assert h.mean() is not None


def test_latency_histogram_handles_zero_and_negative_record():
    h = LatencyHistogram()
    h.record(-1.0)
    h.record(0.5)
    assert h.count() == 1


def test_latency_histogram_quantile_empty_returns_none():
    h = LatencyHistogram()
    assert h.quantile(0.5) is None


def test_latency_histogram_invalid_quantile():
    h = LatencyHistogram()
    with pytest.raises(ValueError):
        h.quantile(1.5)


def test_latency_histogram_constructor_rejects_bad_bounds():
    with pytest.raises(ValueError):
        LatencyHistogram(min_s=0.0, max_s=1.0)


def test_metrics_registry_snapshot():
    reg = MetricsRegistry()
    reg.counter("requests").inc(3)
    reg.adapter_latency("caici").record(0.5)
    reg.adapter_latency("caici").record(1.5)
    reg.sub_test_latency("KMR").record(2.0)
    reg.record_score("KMR", 75.0)
    reg.record_score("KMR", 80.0)
    snap = reg.snapshot()
    assert snap["counters"]["requests"] == 3
    assert snap["adapter_latency"]["caici"]["count"] == 2
    assert snap["sub_test_latency"]["KMR"]["count"] == 1
    assert snap["sub_test_scores"]["KMR"]["n"] == 2
    assert 75.0 <= snap["sub_test_scores"]["KMR"]["mean"] <= 80.0


def test_metrics_registry_prometheus_format_contains_metrics():
    reg = MetricsRegistry()
    reg.counter("requests").inc(2)
    reg.adapter_latency("openai").record(0.1)
    text = reg.format_prometheus()
    assert "stt_requests_total" in text
    assert "stt_adapter_latency_seconds" in text
    assert "adapter=\"openai\"" in text


def test_otel_tracer_span_is_safe_when_disabled():
    tracer = OTelTracer()
    # Even when OTel is not installed, span() must be a usable context manager.
    with tracer.span("x", attributes={"k": "v"}) as span:
        # Either a real span or None depending on environment.
        _ = span
    assert tracer.enabled in (True, False)
