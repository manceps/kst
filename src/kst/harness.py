"""BatteryRunner: orchestrates a KST Index battery run end-to-end.

The runner consumes a :class:`BatteryConfig` (target + adapter +
ordered list of registered sub-test plugins + aggregation parameters)
and emits a :class:`kst.score.KSTIndexReport` plus, when a
:class:`KSTPersistence` is provided, persisted rows across all five
KST tables.

Production guarantees:

- Per-sub-test isolation: any exception raised by a plugin's
  ``build_prompts``, ``parse_response``, or ``score`` is captured,
  stored in :class:`SubTestScore.error` plus
  :attr:`SubTestScore.traceback_text`, and the runner advances to the
  next sub-test.
- Per-sub-test timeout: each plugin executes inside
  :func:`concurrent.futures.ThreadPoolExecutor.submit(...).result(timeout=...)`
  so a wedged plugin cannot block the rest of the battery.
- Concurrency: sub-tests run with configurable parallelism. The
  default is sequential (parallelism=1) because most sub-test rubrics
  expect ordered item dispatch; operators set ``--parallelism N`` for
  embarrassingly-parallel sub-tests.
- Resumability: a SIGINT or SIGTERM transitions the run to
  ``PAUSED`` with all completed sub-tests committed. A subsequent
  ``run --resume <run_id>`` skips those constructs.
- Result persistence: dual sink. Every (Item, AdapterResponse) lands
  in JSONL on disk AND in PostgreSQL. JSONL is the survival mode when
  the database is unavailable; PostgreSQL is the audit-pack channel.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import inspect
import json
import logging
import os
import platform
import signal
import socket
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

from kst.adapters.base import AdapterProtocol, BaseAdapter
from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    RunStatus,
    SubTestScore,
    capture_traceback,
)
from kst.errors import (
    AdapterError,
    ConfigError,
    PersistenceError,
    PluginContractError,
    KSTError,
    TimeoutError as KSTTimeoutError,
)
from kst.observability import MetricsRegistry, OTelTracer
from kst.persistence import KSTPersistence
from kst.protocol import registry as plugin_registry, validate_plugin
from kst.score import (
    AggregationMode,
    KSTIndexReport,
    aggregate_score_report,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Configuration dataclasses.
# ──────────────────────────────────────────────────────────────────────


@dataclass
class SubTestSpec:
    """A reference to a registered plugin plus per-run knobs.

    ``construct_id`` (required) selects the plugin from the registry.
    ``version`` (optional) pins a specific version; when omitted the
    registry returns the latest. ``seed`` is forwarded to the plugin's
    ``build_prompts``. ``weight`` is mandatory only when the run uses
    :class:`AggregationMode.WEIGHTED`.

    ``n_items_cap`` is an optional upper bound on the number of items
    the plugin's ``build_prompts`` is permitted to emit per construct.
    When ``None`` the plugin emits its full item pool. Plugins are
    expected to honour the cap as a deterministic prefix of the
    seed-ordered item stream so that a smoke run remains a strict
    subset of the corresponding full run for the same seed.
    """

    construct_id: str
    version: Optional[str] = None
    seed: int = 0
    weight: Optional[float] = None
    enabled: bool = True
    n_items_cap: Optional[int] = None


@dataclass
class BatteryConfig:
    """Inputs to a battery run.

    The runner validates the config against the plugin registry and
    the adapter's capabilities at start-time. Any inconsistency
    (missing plugin, adapter capability mismatch, weights not summing
    to 1.0) raises :class:`ConfigError` before any prompt is dispatched.

    The ``adapter_timeout_s``, ``adapter_max_attempts``, and
    ``adapter_rpm`` knobs are operator-configurable per-target adapter
    settings surfaced through ``--tests-config`` so a battery can raise
    its adapter timeout above a high-latency target's per-call p95
    without code changes. The defaults match the
    :class:`kst.adapters.base.BaseAdapter` defaults so omitting them
    preserves v1.0.0 behaviour exactly.
    """

    target: str
    adapter_name: str
    sub_tests: List[SubTestSpec]
    aggregation_mode: AggregationMode = AggregationMode.WEIGHTED
    per_sub_test_timeout_s: float = 300.0
    per_battery_timeout_s: Optional[float] = None
    parallelism: int = 1
    n_bootstrap: int = 1000
    seed: int = 1234
    notes: str = ""
    # Operator-configurable adapter knobs. ``None`` means "fall back to
    # the adapter's own default", which preserves v1.0.0 semantics.
    adapter_timeout_s: Optional[float] = None
    adapter_max_attempts: Optional[int] = None
    adapter_rpm: Optional[int] = None

    def weights_map(self) -> Dict[str, float]:
        m: Dict[str, float] = {}
        for s in self.sub_tests:
            if not s.enabled:
                continue
            if s.weight is None:
                continue
            m[s.construct_id] = float(s.weight)
        return m

    def expected_constructs(self) -> List[str]:
        return [s.construct_id for s in self.sub_tests if s.enabled]


@dataclass
class JSONLSink:
    """A line-buffered JSONL writer used as the file-system mirror.

    The runner writes one envelope per Item-Response pair. The file
    handle is held open for the duration of the run and flushed after
    every record so a kill-9 still leaves a recoverable trail.
    """

    path: str
    _handle: Optional[Any] = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._handle = open(self.path, "a", encoding="utf-8")

    def write(self, record: Dict[str, Any]) -> None:
        if self._handle is None:
            return
        line = json.dumps(record, default=str, ensure_ascii=False)
        with self._lock:
            self._handle.write(line)
            self._handle.write("\n")
            self._handle.flush()
            os.fsync(self._handle.fileno())

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                try:
                    self._handle.flush()
                    os.fsync(self._handle.fileno())
                finally:
                    self._handle.close()
                    self._handle = None


@dataclass
class BatteryRunResult:
    """What a finished BatteryRunner returns to the caller."""

    run_id: str
    status: RunStatus
    report: Optional[KSTIndexReport]
    sub_test_scores: List[SubTestScore]
    error: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# Runner.
# ──────────────────────────────────────────────────────────────────────


class BatteryRunner:
    """End-to-end battery orchestrator.

    Construct once, call :meth:`run` once. Reuse across runs is
    explicitly disallowed: every run consumes a fresh BatteryConfig
    and emits a fresh run_id so the audit trail is unambiguous.
    """

    def __init__(
        self,
        *,
        config: BatteryConfig,
        adapter: AdapterProtocol,
        persistence: Optional[KSTPersistence] = None,
        jsonl_sink: Optional[JSONLSink] = None,
        metrics: Optional[MetricsRegistry] = None,
        tracer: Optional[OTelTracer] = None,
        resume_run_id: Optional[str] = None,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.persistence = persistence
        self.jsonl_sink = jsonl_sink
        self.metrics = metrics or MetricsRegistry()
        self.tracer = tracer or OTelTracer()
        self.resume_run_id = resume_run_id

        self._stop_event = threading.Event()
        self._scores: List[SubTestScore] = []
        self._completed_constructs: List[str] = []
        self._run_id: str = resume_run_id or str(uuid.uuid4())

    # ── Public entry points ──────────────────────────────────────────

    @property
    def run_id(self) -> str:
        return self._run_id

    def request_stop(self) -> None:
        """Mark the runner for graceful shutdown after the current sub-test."""
        self._stop_event.set()

    def run(self) -> BatteryRunResult:
        """Execute the configured battery and return the result.

        Persists every sub-test result as it lands, so a kill-9
        between sub-tests still leaves the audit trail intact for the
        already-finished tests.
        """
        run_status = RunStatus.PENDING
        try:
            self._validate_config_against_adapter()
            plugins = self._resolve_plugins()

            env_payload = _environment_metadata()
            env_payload.update(
                {
                    "harness_pid": os.getpid(),
                    "harness_started_at": time.time(),
                }
            )

            if self.persistence is not None:
                if self.resume_run_id:
                    completed = self.persistence.resume_check(self.resume_run_id)
                    self._completed_constructs = list(completed)
                    self._run_id = self.resume_run_id
                    logger.info(
                        "stt.harness resuming run_id=%s completed=%d/%d",
                        self._run_id, len(completed), len(plugins),
                    )
                else:
                    self._run_id = self.persistence.create_run(
                        target=self.config.target,
                        adapter_name=self.config.adapter_name,
                        capability=getattr(
                            self.adapter, "capability", AdapterCapability.BLACK_BOX
                        ),
                        aggregation_mode=self.config.aggregation_mode.value,
                        weights=self.config.weights_map(),
                        expected_constructs=self.config.expected_constructs(),
                        environment=env_payload,
                        notes=self.config.notes,
                    )
                self.persistence.mark_running(self._run_id)
            run_status = RunStatus.RUNNING

            started_at = time.time()
            self._install_signal_handlers()

            with self.tracer.span(
                "stt.battery.run",
                attributes={
                    "stt.run_id": self._run_id,
                    "stt.target": self.config.target,
                    "stt.adapter_name": self.config.adapter_name,
                    "stt.parallelism": self.config.parallelism,
                    "stt.n_sub_tests": len(plugins),
                },
            ):
                if self.config.parallelism > 1:
                    self._execute_parallel(plugins)
                else:
                    self._execute_sequential(plugins)

            if self._stop_event.is_set():
                run_status = RunStatus.PAUSED
                if self.persistence is not None:
                    self.persistence.mark_paused(self._run_id)
                return BatteryRunResult(
                    run_id=self._run_id,
                    status=run_status,
                    report=None,
                    sub_test_scores=list(self._scores),
                )

            finished_at = time.time()
            try:
                report = aggregate_score_report(
                    self._scores,
                    target=self.config.target,
                    adapter_name=self.config.adapter_name,
                    capability=getattr(
                        self.adapter, "capability", AdapterCapability.BLACK_BOX
                    ).value,
                    run_id=self._run_id,
                    mode=self.config.aggregation_mode,
                    weights=(
                        self.config.weights_map()
                        if self.config.aggregation_mode == AggregationMode.WEIGHTED
                        else None
                    ),
                    expected_constructs=self.config.expected_constructs(),
                    environment=env_payload,
                    n_bootstrap=self.config.n_bootstrap,
                    seed=self.config.seed,
                    started_at=started_at,
                    finished_at=finished_at,
                    notes=self.config.notes,
                )
            except KSTError:
                if self.persistence is not None:
                    self.persistence.mark_failed(
                        self._run_id, notes="aggregation_failed"
                    )
                raise

            if self.persistence is not None:
                self.persistence.upsert_score_aggregate(report)
                self.persistence.mark_completed(self._run_id)
            run_status = RunStatus.COMPLETED
            return BatteryRunResult(
                run_id=self._run_id,
                status=run_status,
                report=report,
                sub_test_scores=list(self._scores),
            )
        except KSTError as exc:
            if self.persistence is not None:
                try:
                    self.persistence.mark_failed(
                        self._run_id, notes=type(exc).__name__
                    )
                except PersistenceError:
                    logger.exception("mark_failed failed for run_id=%s", self._run_id)
            return BatteryRunResult(
                run_id=self._run_id,
                status=RunStatus.FAILED,
                report=None,
                sub_test_scores=list(self._scores),
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("stt.harness fatal error")
            if self.persistence is not None:
                try:
                    self.persistence.mark_failed(
                        self._run_id, notes="unhandled_exception"
                    )
                except PersistenceError:
                    pass
            return BatteryRunResult(
                run_id=self._run_id,
                status=RunStatus.FAILED,
                report=None,
                sub_test_scores=list(self._scores),
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            self._restore_signal_handlers()
            if self.jsonl_sink is not None:
                try:
                    self.jsonl_sink.close()
                except Exception:  # noqa: BLE001
                    logger.exception("jsonl_sink close failed")

    # ── Validation ───────────────────────────────────────────────────

    def _validate_config_against_adapter(self) -> None:
        if not isinstance(self.config, BatteryConfig):
            raise ConfigError("config must be a BatteryConfig.")
        if not self.config.sub_tests:
            raise ConfigError("BatteryConfig.sub_tests must be non-empty.")
        if self.config.parallelism < 1:
            raise ConfigError(
                f"parallelism must be >= 1; got {self.config.parallelism}.",
            )
        if self.config.aggregation_mode == AggregationMode.WEIGHTED:
            weights = self.config.weights_map()
            if len(weights) != len(self.config.expected_constructs()):
                raise ConfigError(
                    "weighted aggregation requires a weight for every "
                    "enabled sub-test.",
                    context={
                        "n_weights": len(weights),
                        "n_enabled": len(self.config.expected_constructs()),
                    },
                )

    def _resolve_plugins(self) -> List[Tuple[SubTestSpec, Any]]:
        out: List[Tuple[SubTestSpec, Any]] = []
        adapter_capability = getattr(
            self.adapter, "capability", AdapterCapability.BLACK_BOX
        )
        for spec in self.config.sub_tests:
            if not spec.enabled:
                continue
            try:
                plugin = plugin_registry.get(spec.construct_id, spec.version)
            except KeyError as exc:
                raise ConfigError(
                    f"sub-test plugin not registered: {exc.args[0]!r}",
                    context={
                        "construct_id": spec.construct_id,
                        "version": spec.version,
                    },
                ) from exc
            # Re-validate at run-time as a defence in depth.
            try:
                validate_plugin(plugin)
            except PluginContractError as exc:
                raise ConfigError(
                    f"sub-test plugin {spec.construct_id!r} failed contract "
                    f"re-validation: {exc.message}",
                    context=dict(exc.context),
                ) from exc
            # Applicability check.
            modes = plugin.applicability_modes
            if isinstance(modes, ApplicabilityMode):
                modes = (modes,)
            allowed = False
            for m in modes:
                if m == ApplicabilityMode.BOTH:
                    allowed = True
                    break
                if (
                    m == ApplicabilityMode.GREY_BOX
                    and adapter_capability == AdapterCapability.GREY_BOX
                ):
                    allowed = True
                    break
                if (
                    m == ApplicabilityMode.BLACK_BOX
                    and adapter_capability == AdapterCapability.BLACK_BOX
                ):
                    allowed = True
                    break
            if not allowed:
                raise ConfigError(
                    f"sub-test {spec.construct_id!r} cannot be run against "
                    f"adapter capability {adapter_capability.value}.",
                    context={
                        "construct_id": spec.construct_id,
                        "applicability_modes": [
                            getattr(m, "value", str(m)) for m in modes
                        ],
                        "adapter_capability": adapter_capability.value,
                    },
                )
            out.append((spec, plugin))
        return out

    # ── Execution paths ──────────────────────────────────────────────

    def _execute_sequential(
        self, plugins: List[Tuple[SubTestSpec, Any]]
    ) -> None:
        for spec, plugin in plugins:
            if self._stop_event.is_set():
                logger.info(
                    "stt.harness stop requested; "
                    "skipping construct_id=%s",
                    spec.construct_id,
                )
                break
            if plugin.get_construct_id() in self._completed_constructs:
                logger.info(
                    "stt.harness resume: skipping completed construct_id=%s",
                    plugin.get_construct_id(),
                )
                continue
            score = self._execute_one_sub_test(spec, plugin)
            self._scores.append(score)
            if score.error is None:
                self._completed_constructs.append(plugin.get_construct_id())
                if self.persistence is not None:
                    try:
                        self.persistence.mark_construct_completed(
                            self._run_id, plugin.get_construct_id()
                        )
                    except PersistenceError:
                        logger.exception(
                            "mark_construct_completed failed for %s",
                            plugin.get_construct_id(),
                        )

    def _execute_parallel(
        self, plugins: List[Tuple[SubTestSpec, Any]]
    ) -> None:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.parallelism,
            thread_name_prefix="stt-sub",
        ) as pool:
            futures: Dict[concurrent.futures.Future, Tuple[SubTestSpec, Any]] = {}
            for spec, plugin in plugins:
                if plugin.get_construct_id() in self._completed_constructs:
                    logger.info(
                        "stt.harness resume: skipping completed construct_id=%s",
                        plugin.get_construct_id(),
                    )
                    continue
                fut = pool.submit(self._execute_one_sub_test, spec, plugin)
                futures[fut] = (spec, plugin)
            for fut in concurrent.futures.as_completed(futures):
                spec, plugin = futures[fut]
                if self._stop_event.is_set():
                    break
                try:
                    score = fut.result()
                except Exception as exc:  # noqa: BLE001
                    score = self._error_score(
                        spec, plugin, exc,
                        prefix="parallel worker raised",
                    )
                self._scores.append(score)
                if score.error is None:
                    self._completed_constructs.append(
                        plugin.get_construct_id()
                    )
                    if self.persistence is not None:
                        try:
                            self.persistence.mark_construct_completed(
                                self._run_id, plugin.get_construct_id()
                            )
                        except PersistenceError:
                            logger.exception(
                                "mark_construct_completed failed for %s",
                                plugin.get_construct_id(),
                            )

    def _execute_one_sub_test(
        self, spec: SubTestSpec, plugin: Any
    ) -> SubTestScore:
        construct_id = plugin.get_construct_id()
        version = plugin.get_version()
        start = time.monotonic()
        with self.tracer.span(
            "stt.sub_test.run",
            attributes={
                "stt.construct_id": construct_id,
                "stt.version": version,
                "stt.seed": spec.seed,
            },
        ):
            try:
                # Each sub-test runs inside a single-thread pool so we
                # can enforce a deterministic per-sub-test timeout.
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix=f"stt-{construct_id}",
                ) as inner:
                    fut = inner.submit(
                        self._dispatch_and_score, spec, plugin
                    )
                    score = fut.result(
                        timeout=self.config.per_sub_test_timeout_s
                    )
            except concurrent.futures.TimeoutError as exc:
                self.metrics.counter("sub_test_timeouts").inc()
                score = self._error_score(
                    spec, plugin, exc, prefix="per-sub-test timeout",
                )
            except Exception as exc:  # noqa: BLE001
                score = self._error_score(spec, plugin, exc)
        duration = time.monotonic() - start
        score.duration_s = duration
        self.metrics.sub_test_latency(construct_id).record(duration)
        self.metrics.record_score(construct_id, score.normalized)
        if self.persistence is not None:
            try:
                self.persistence.insert_sub_test_result(self._run_id, score)
            except PersistenceError:
                logger.exception(
                    "persist sub_test_result failed for %s", construct_id,
                )
        if self.jsonl_sink is not None:
            self.jsonl_sink.write(
                {
                    "type": "sub_test_score",
                    "run_id": self._run_id,
                    "score": _score_to_jsonable(score),
                }
            )
        return score

    def _dispatch_and_score(
        self, spec: SubTestSpec, plugin: Any
    ) -> SubTestScore:
        construct_id = plugin.get_construct_id()
        version = plugin.get_version()
        parsed_set: List[Parsed] = []
        n_parse_errors = 0
        n_items = 0
        # Pass n_items_cap only to plugins whose build_prompts signature
        # accepts it; v1.0.0 plugin authors who have not yet adopted the
        # smoke-burst cap still see the legacy build_prompts(seed) call.
        prompt_kwargs: Dict[str, Any] = {}
        if spec.n_items_cap is not None and _build_prompts_accepts_cap(plugin):
            prompt_kwargs["n_items_cap"] = spec.n_items_cap
        for item in plugin.build_prompts(spec.seed, **prompt_kwargs):
            if self._stop_event.is_set():
                break
            n_items += 1
            adapter_req = AdapterRequest(
                prompt=item.prompt,
                system=item.system,
                test_id=construct_id,
                construct_id=construct_id,
                item_id=item.item_id,
                sub_test_version=version,
                temperature=item.temperature,
                max_tokens=item.max_tokens,
                seed=item.seed,
                stop_sequences=list(item.stop_sequences),
                metadata=dict(item.meta),
            )
            adapter_resp = self._send_with_metrics(adapter_req)
            if self.persistence is not None:
                try:
                    self.persistence.insert_response_record(
                        self._run_id,
                        construct_id,
                        version,
                        item,
                        adapter_req,
                        adapter_resp,
                    )
                except PersistenceError:
                    logger.exception(
                        "persist response_record failed for request_id=%s",
                        adapter_req.request_id,
                    )
            if self.jsonl_sink is not None:
                self.jsonl_sink.write(
                    {
                        "type": "response_record",
                        "run_id": self._run_id,
                        "construct_id": construct_id,
                        "version": version,
                        "item_id": item.item_id,
                        "request": dataclasses.asdict(adapter_req),
                        "response": _response_to_jsonable(adapter_resp),
                    }
                )
            try:
                parsed = plugin.parse_response(item, adapter_resp)
                if parsed.error:
                    n_parse_errors += 1
            except Exception as exc:  # noqa: BLE001
                n_parse_errors += 1
                parsed = Parsed(
                    item_id=item.item_id,
                    error=f"{type(exc).__name__}: {exc}",
                    raw_text=adapter_resp.text,
                )
            parsed_set.append(parsed)
        score = plugin.score(parsed_set)
        if not isinstance(score, SubTestScore):
            raise ConfigError(
                f"sub-test {construct_id!r} score() returned a "
                f"{type(score).__name__}; expected SubTestScore.",
            )
        score.n_items = score.n_items or n_items
        score.n_parse_errors = score.n_parse_errors or n_parse_errors
        return score

    def _send_with_metrics(
        self, request: AdapterRequest
    ) -> AdapterResponse:
        adapter_name = getattr(self.adapter, "name", "unknown")
        self.metrics.counter("adapter_requests").inc()
        start = time.monotonic()
        try:
            if isinstance(self.adapter, BaseAdapter):
                resp = self.adapter.send_adapter(request)
            else:
                # Adapters that implement the older TargetRequest path.
                legacy_req = request.to_target_request()
                legacy_resp = self.adapter.send(legacy_req)
                resp = AdapterResponse.from_target_response(legacy_resp)
        finally:
            self.metrics.adapter_latency(adapter_name).record(
                time.monotonic() - start
            )
        if resp.status_code != 200:
            self.metrics.counter("adapter_non_200").inc()
        return resp

    def _error_score(
        self,
        spec: SubTestSpec,
        plugin: Any,
        exc: BaseException,
        *,
        prefix: str = "sub-test raised",
    ) -> SubTestScore:
        tb = capture_traceback(exc)
        return SubTestScore(
            test_id=plugin.get_name(),
            test_name=plugin.get_name(),
            construct_id=plugin.get_construct_id(),
            version=plugin.get_version(),
            score=0.0,
            max_score=100.0,
            error=f"{prefix}: {type(exc).__name__}: {exc}",
            traceback_text=tb,
        )

    # ── Signal handling ──────────────────────────────────────────────

    _SIGNALS = (signal.SIGINT, signal.SIGTERM)

    def _install_signal_handlers(self) -> None:
        self._prev_handlers: Dict[int, Any] = {}
        # Only the main thread can install signal handlers; defer
        # silently on worker threads (parallel sub-test execution does
        # not need its own handlers, the main thread's apply).
        if threading.current_thread() is not threading.main_thread():
            return
        for sig in self._SIGNALS:
            try:
                self._prev_handlers[sig] = signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                # Signal not available on this platform.
                continue

    def _restore_signal_handlers(self) -> None:
        for sig, prev in getattr(self, "_prev_handlers", {}).items():
            try:
                signal.signal(sig, prev)
            except (ValueError, OSError):
                continue

    def _on_signal(self, signum: int, frame: Any) -> None:  # noqa: ARG002
        logger.warning(
            "stt.harness received signal %d; requesting graceful shutdown.",
            signum,
        )
        self.request_stop()


# ──────────────────────────────────────────────────────────────────────
# Serialization helpers.
# ──────────────────────────────────────────────────────────────────────


def _response_to_jsonable(resp: AdapterResponse) -> Dict[str, Any]:
    payload = dataclasses.asdict(resp)
    cap = payload.get("capability")
    if isinstance(cap, AdapterCapability):
        payload["capability"] = cap.value
    return payload


def _score_to_jsonable(score: SubTestScore) -> Dict[str, Any]:
    return dataclasses.asdict(score)


def _build_prompts_accepts_cap(plugin: Any) -> bool:
    """Return True iff ``plugin.build_prompts`` accepts an ``n_items_cap`` kwarg.

    Plugin authors opt into the smoke-burst cap by extending their
    ``build_prompts`` signature to ``build_prompts(self, seed, *, n_items_cap=None)``.
    Plugins that have not yet adopted the cap are honoured at their
    v1.0.0 contract: the harness calls ``build_prompts(seed)`` only.
    """
    fn = getattr(plugin, "build_prompts", None)
    if fn is None or not callable(fn):
        return False
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if "n_items_cap" in params:
        return True
    # An adapter that exposes **kwargs also accepts n_items_cap.
    for p in params.values():
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False


def _environment_metadata() -> Dict[str, Any]:
    """Minimum-viable environment metadata for the run row."""
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "argv": list(sys.argv),
        "cwd": os.getcwd(),
    }


__all__ = [
    "BatteryConfig",
    "BatteryRunResult",
    "BatteryRunner",
    "JSONLSink",
    "SubTestSpec",
]
