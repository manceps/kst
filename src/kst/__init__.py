"""KST (Kari Sapience Test) Harness.

The KST harness is the production harness for Manceps' contribution to
the industry-standard sapience benchmark. It ingests named sub-tests
via a strict plugin protocol, administers them through pluggable
adapters, collects raw text, structured outputs, and grey-box
architectural-state telemetry, scores per-test rubrics with bootstrap
confidence intervals, and aggregates the results into a single 0 to
100 KST Index report.

The harness CORE (this module) is production-ready and audit-pack
defensible. Sub-test plugins land as a follow-on engagement once the
parallel research workstream synthesises expert proposals.

Author: Al Kari, Manceps Inc.
"""

from kst.envelope import (
    AdapterCapabilities,
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    ApplicabilityMode,
    GreyBoxTelemetry,
    HarnessReport,
    Item,
    Parsed,
    RunStatus,
    ScoreInterval,
    SubTestResult,
    SubTestScore,
    TargetRequest,
    TargetResponse,
    capture_traceback,
    from_dict_report,
)
from kst.errors import (
    AdapterError,
    ConfigError,
    IncompleteBatteryError,
    PersistenceError,
    PluginContractError,
    RateLimitError,
    ResumeError,
    KSTError,
    ScoreValidationError,
    TimeoutError,
)
from kst.protocol import (
    SubTestProtocol,
    list_plugins,
    register_plugin,
    registry,
)
from kst.score import (
    AggregationMode,
    KSTIndexReport,
    aggregate_score_report,
    aggregate_scores,
    bootstrap_ci,
    differential_item_functioning,
    krippendorff_alpha_interval,
)

__all__ = [
    # Envelope types.
    "AdapterCapabilities",
    "AdapterCapability",
    "AdapterRequest",
    "AdapterResponse",
    "ApplicabilityMode",
    "GreyBoxTelemetry",
    "HarnessReport",
    "Item",
    "Parsed",
    "RunStatus",
    "ScoreInterval",
    "SubTestResult",
    "SubTestScore",
    "TargetRequest",
    "TargetResponse",
    "capture_traceback",
    "from_dict_report",
    # Errors.
    "AdapterError",
    "ConfigError",
    "IncompleteBatteryError",
    "PersistenceError",
    "PluginContractError",
    "RateLimitError",
    "ResumeError",
    "KSTError",
    "ScoreValidationError",
    "TimeoutError",
    # Protocol + plugin registry.
    "SubTestProtocol",
    "list_plugins",
    "register_plugin",
    "registry",
    # Scoring.
    "AggregationMode",
    "KSTIndexReport",
    "aggregate_score_report",
    "aggregate_scores",
    "bootstrap_ci",
    "differential_item_functioning",
    "krippendorff_alpha_interval",
]
