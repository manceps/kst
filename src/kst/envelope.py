"""Canonical request, response, and report envelopes for the KST harness.

All cross-component data in the KST harness flows through these
dataclasses. Adapters consume :class:`TargetRequest` and emit
:class:`TargetResponse`. Sub-tests emit :class:`SubTestResult`. The
harness driver aggregates results into :class:`HarnessReport`, which
serializes deterministically to JSON for downstream tooling and to a
human-readable Markdown for the external document.

Grey-box adapters (only CAI.CI today) attach a
:class:`GreyBoxTelemetry` payload to the response so the sub-test
rubrics that score on architectural state (epistemic state,
calibration, AGS drift, etc.) can do their work.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class AdapterCapability(str, Enum):
    """Declares what an adapter can return to the harness.

    BLACK_BOX adapters return only the model's free-form text and
    minimal API metadata (model id, latency). GREY_BOX adapters
    additionally surface architectural-state telemetry such as
    epistemic state, confidence, calibration, AGS drift flags.
    """

    BLACK_BOX = "black_box"
    GREY_BOX = "grey_box"


@dataclass
class GreyBoxTelemetry:
    """Architectural-state telemetry for grey-box scoring.

    Only populated by adapters that have introspective access to the
    target system. Maps the 20-signal envelope surfaced by CAI.CI's
    interaction-engine telemetry layer; foreign systems will leave
    most fields as ``None``.
    """

    epistemic_state: Optional[str] = None
    confidence: Optional[float] = None
    calibration_score: Optional[float] = None
    valence: Optional[float] = None
    arousal: Optional[float] = None
    seeking_drive: Optional[float] = None
    competence: Optional[float] = None
    meta_competence: Optional[float] = None
    workspace_selectivity: Optional[float] = None
    ags_state: Optional[str] = None
    ags_drift_flag: Optional[bool] = None
    factual_claim_audit: Optional[Dict[str, Any]] = None
    tool_routing: Optional[Dict[str, Any]] = None
    voice: Optional[Dict[str, Any]] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class TargetRequest:
    """A single prompt the harness sends to the target AI system."""

    prompt: str
    system: Optional[str] = None
    test_id: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    temperature: float = 0.0
    max_tokens: int = 512
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetResponse:
    """The adapter's reply to a :class:`TargetRequest`.

    ``text`` is the free-form response. ``structured`` is whatever
    machine-parseable shape the sub-test asked for (often empty).
    ``telemetry`` is grey-box only. ``status_code`` and ``latency_s``
    let the harness flag transport failures vs scoring failures.
    """

    request_id: str
    text: str
    model_id: str
    adapter_name: str
    capability: AdapterCapability
    status_code: int = 200
    latency_s: float = 0.0
    structured: Dict[str, Any] = field(default_factory=dict)
    telemetry: Optional[GreyBoxTelemetry] = None
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class SubTestResult:
    """A single sub-test's verdict on a single target."""

    test_id: str
    test_name: str
    score: float
    max_score: float = 100.0
    notes: str = ""
    sub_scores: Dict[str, float] = field(default_factory=dict)
    requests: List[TargetRequest] = field(default_factory=list)
    responses: List[TargetResponse] = field(default_factory=list)
    duration_s: float = 0.0
    error: Optional[str] = None

    @property
    def normalized(self) -> float:
        """Return the score on a 0..100 scale."""
        if self.max_score <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * self.score / self.max_score))


@dataclass
class HarnessReport:
    """Full battery output for one (target, run) pair."""

    target: str
    adapter_name: str
    capability: AdapterCapability
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    sub_tests: List[SubTestResult] = field(default_factory=list)
    index_score: float = 0.0
    aggregation_mode: str = "weighted"
    weights: Dict[str, float] = field(default_factory=dict)
    notes: str = ""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic JSON-ready dict (enums stringified, nested OK)."""

        def _convert(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj

        return _convert(asdict(self))

    def to_json(self, indent: int = 2) -> str:
        """Serialize the report to JSON for downstream tooling."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_markdown(self) -> str:
        """Human-readable Markdown for the external document."""
        lines: List[str] = []
        lines.append(f"# KST Index report: {self.target}")
        lines.append("")
        lines.append(f"- Adapter: `{self.adapter_name}` ({self.capability.value})")
        lines.append(f"- Run ID: `{self.run_id}`")
        lines.append(f"- Aggregation: `{self.aggregation_mode}`")
        lines.append(f"- Index score: **{self.index_score:.2f} / 100**")
        lines.append("")
        lines.append("## Sub-test scores")
        lines.append("")
        lines.append("| Test ID | Test name | Score | Max | Normalized |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in self.sub_tests:
            lines.append(
                f"| {r.test_id} | {r.test_name} | "
                f"{r.score:.2f} | {r.max_score:.2f} | "
                f"{r.normalized:.2f} |"
            )
        if self.notes:
            lines.append("")
            lines.append("## Notes")
            lines.append("")
            lines.append(self.notes)
        lines.append("")
        return "\n".join(lines)


class RunStatus(str, Enum):
    """Lifecycle status of a battery run row in persistence.

    PENDING: the run row has been created and reserved a run_id but no
    sub-tests have completed.

    RUNNING: at least one sub-test has been dispatched.

    PAUSED: the runner caught SIGTERM/SIGINT and committed its
    last-completed sub-test offset to the database; a subsequent
    ``run --resume <run_id>`` continues from the next pending sub-test.

    COMPLETED: every sub-test landed (success or error) and the
    aggregate index was computed.

    FAILED: the run aborted irrecoverably before all sub-tests landed
    (configuration error, persistence outage, manual abort).
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ApplicabilityMode(str, Enum):
    """Declares which target classes a sub-test can be administered to."""

    BLACK_BOX = "black_box"
    GREY_BOX = "grey_box"
    BOTH = "both"


@dataclass
class AdapterCapabilities:
    """Static declaration of what an adapter exposes.

    Mirrors the rate-limit and feature surface every production adapter
    publishes so the BatteryRunner can plan concurrency and back off
    without trial-and-error.
    """

    name: str
    capability: AdapterCapability
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    supports_seed: bool = False
    supports_logprobs: bool = False
    supports_grey_box_telemetry: bool = False
    max_tokens: int = 4096
    default_model_id: str = ""


@dataclass
class AdapterRequest:
    """A single prompt the harness sends to the target AI system.

    Production-grade superset of :class:`TargetRequest`. The new fields
    are required by sub-test plugins that pin seeds, request logprobs,
    or attach sub-test bookkeeping (``construct_id``, ``item_id``,
    ``sub_test_version``) for traceability.
    """

    prompt: str
    system: Optional[str] = None
    test_id: str = ""
    construct_id: str = ""
    item_id: str = ""
    sub_test_version: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    temperature: float = 0.0
    max_tokens: int = 512
    seed: Optional[int] = None
    request_logprobs: bool = False
    stop_sequences: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_target_request(self) -> "TargetRequest":
        """Down-convert to the legacy :class:`TargetRequest` for the existing adapter base."""
        return TargetRequest(
            prompt=self.prompt,
            system=self.system,
            test_id=self.test_id,
            request_id=self.request_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            metadata={
                **self.metadata,
                "construct_id": self.construct_id,
                "item_id": self.item_id,
                "sub_test_version": self.sub_test_version,
                "seed": self.seed,
                "request_logprobs": self.request_logprobs,
                "stop_sequences": list(self.stop_sequences),
            },
        )

    @classmethod
    def from_target_request(cls, tr: "TargetRequest") -> "AdapterRequest":
        """Up-convert a legacy :class:`TargetRequest` for harness-side handling."""
        md = dict(tr.metadata or {})
        return cls(
            prompt=tr.prompt,
            system=tr.system,
            test_id=tr.test_id,
            construct_id=str(md.pop("construct_id", "") or ""),
            item_id=str(md.pop("item_id", "") or ""),
            sub_test_version=str(md.pop("sub_test_version", "") or ""),
            request_id=tr.request_id,
            temperature=tr.temperature,
            max_tokens=tr.max_tokens,
            seed=md.pop("seed", None),
            request_logprobs=bool(md.pop("request_logprobs", False)),
            stop_sequences=list(md.pop("stop_sequences", []) or []),
            metadata=md,
        )


@dataclass
class AdapterResponse:
    """Adapter reply, production-grade superset of :class:`TargetResponse`.

    Adds ``grey_box_telemetry`` (alias kept alongside ``telemetry`` for
    contract clarity), ``logprobs``, ``attempts``, and
    ``rate_limit_observed`` for downstream auditors and rate planners.
    """

    request_id: str
    text: str
    model_id: str
    adapter_name: str
    capability: AdapterCapability
    status_code: int = 200
    latency_s: float = 0.0
    structured: Dict[str, Any] = field(default_factory=dict)
    grey_box_telemetry: Optional[GreyBoxTelemetry] = None
    logprobs: Optional[Dict[str, Any]] = None
    attempts: int = 1
    rate_limit_observed: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    @property
    def telemetry(self) -> Optional[GreyBoxTelemetry]:
        """Back-compat read alias for ``grey_box_telemetry``."""
        return self.grey_box_telemetry

    @classmethod
    def from_target_response(cls, tr: "TargetResponse") -> "AdapterResponse":
        return cls(
            request_id=tr.request_id,
            text=tr.text,
            model_id=tr.model_id,
            adapter_name=tr.adapter_name,
            capability=tr.capability,
            status_code=tr.status_code,
            latency_s=tr.latency_s,
            structured=dict(tr.structured),
            grey_box_telemetry=tr.telemetry,
            error=tr.error,
            raw=tr.raw,
        )


@dataclass
class Item:
    """One prompt-bearing unit produced by a sub-test's :meth:`build_prompts`.

    Sub-tests own item construction; the harness only consumes the
    iterable. ``item_id`` is unique within the sub-test; ``meta`` is
    sub-test-private payload that ``parse_response`` and ``score`` may
    consult (gold answer, stratum, etc.).
    """

    item_id: str
    prompt: str
    system: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    seed: Optional[int] = None
    max_tokens: int = 512
    temperature: float = 0.0
    stop_sequences: List[str] = field(default_factory=list)


@dataclass
class Parsed:
    """Sub-test-specific parse of one :class:`AdapterResponse`.

    The harness treats ``payload`` as opaque; downstream scoring
    consumes the structured shape the sub-test defined. ``error`` is
    populated when the parse failed (malformed output, refusal, etc.)
    so the sub-test's :meth:`score` can decide how to weight or drop
    the item.
    """

    item_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    raw_text: str = ""


@dataclass
class ScoreInterval:
    """Bootstrap confidence interval on a scalar score."""

    lower: float
    upper: float
    confidence: float = 0.95
    n_bootstrap: int = 0

    def width(self) -> float:
        return float(self.upper - self.lower)


@dataclass
class SubTestScore:
    """A sub-test plugin's verdict, production-grade.

    Superset of :class:`SubTestResult` with explicit CI, per-stratum
    breakdown, and a ``trace`` payload the harness can persist for
    audit. The harness wraps this into the legacy
    :class:`SubTestResult` for back-compat with the existing report
    types until the legacy shape is retired.
    """

    test_id: str
    test_name: str
    construct_id: str
    version: str
    score: float
    max_score: float = 100.0
    notes: str = ""
    sub_scores: Dict[str, float] = field(default_factory=dict)
    per_stratum: Dict[str, float] = field(default_factory=dict)
    n_items: int = 0
    n_parse_errors: int = 0
    ci: Optional[ScoreInterval] = None
    duration_s: float = 0.0
    trace: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    traceback_text: Optional[str] = None

    @property
    def normalized(self) -> float:
        """Score on a 0..100 scale, deterministically clamped."""
        if self.max_score <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * self.score / self.max_score))

    def to_sub_test_result(
        self,
        requests: Optional[List["TargetRequest"]] = None,
        responses: Optional[List["TargetResponse"]] = None,
    ) -> "SubTestResult":
        """Back-compat: emit the legacy :class:`SubTestResult` shape."""
        return SubTestResult(
            test_id=self.test_id,
            test_name=self.test_name,
            score=self.score,
            max_score=self.max_score,
            notes=self.notes,
            sub_scores=dict(self.sub_scores),
            requests=list(requests or []),
            responses=list(responses or []),
            duration_s=self.duration_s,
            error=self.error,
        )


def capture_traceback(exc: BaseException) -> str:
    """Render an exception's full traceback for persistence."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def from_dict_report(payload: Dict[str, Any]) -> HarnessReport:
    """Round-trip a JSON payload back into a :class:`HarnessReport`.

    Best-effort: enum fields are coerced; nested dataclasses are
    reconstructed; unknown keys are dropped silently to support
    forward compatibility with future schema additions.
    """
    cap_raw = payload.get("capability", AdapterCapability.BLACK_BOX.value)
    cap = AdapterCapability(cap_raw)

    sub_tests_in = payload.get("sub_tests", []) or []
    sub_tests: List[SubTestResult] = []
    for s in sub_tests_in:
        reqs_in = s.get("requests", []) or []
        resps_in = s.get("responses", []) or []
        reqs = [TargetRequest(**_filter(r, TargetRequest)) for r in reqs_in]
        resps_out: List[TargetResponse] = []
        for r in resps_in:
            tele = r.get("telemetry")
            if isinstance(tele, dict):
                tele_obj = GreyBoxTelemetry(**_filter(tele, GreyBoxTelemetry))
            else:
                tele_obj = None
            r_copy = dict(r)
            r_copy["telemetry"] = tele_obj
            r_copy["capability"] = AdapterCapability(
                r_copy.get("capability", AdapterCapability.BLACK_BOX.value)
            )
            resps_out.append(TargetResponse(**_filter(r_copy, TargetResponse)))
        sub_tests.append(
            SubTestResult(
                test_id=s.get("test_id", ""),
                test_name=s.get("test_name", ""),
                score=float(s.get("score", 0.0)),
                max_score=float(s.get("max_score", 100.0)),
                notes=s.get("notes", ""),
                sub_scores=dict(s.get("sub_scores", {})),
                requests=reqs,
                responses=resps_out,
                duration_s=float(s.get("duration_s", 0.0)),
                error=s.get("error"),
            )
        )

    return HarnessReport(
        target=payload.get("target", ""),
        adapter_name=payload.get("adapter_name", ""),
        capability=cap,
        started_at=float(payload.get("started_at", 0.0)),
        finished_at=float(payload.get("finished_at", 0.0)),
        sub_tests=sub_tests,
        index_score=float(payload.get("index_score", 0.0)),
        aggregation_mode=payload.get("aggregation_mode", "weighted"),
        weights=dict(payload.get("weights", {})),
        notes=payload.get("notes", ""),
        run_id=payload.get("run_id", str(uuid.uuid4())),
    )


def _filter(payload: Dict[str, Any], cls: Any) -> Dict[str, Any]:
    """Drop dict keys not in ``cls.__dataclass_fields__`` for forward compat."""
    allowed = set(getattr(cls, "__dataclass_fields__", {}).keys())
    return {k: v for k, v in payload.items() if k in allowed}
