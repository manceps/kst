"""Command-line interface for the KST harness.

Sub-commands:

- ``run``: execute a battery against a named target.
- ``replay``: rehydrate a finished run from PostgreSQL.
- ``compare``: side-by-side a small set of runs.
- ``list-runs``: enumerate runs, filtered by target and since.

Exit codes follow Unix conventions:

- 0: success.
- 1: generic / unhandled exception.
- 2: configuration error.
- 3: adapter unreachable.
- 4: incomplete battery (one or more sub-tests missing or failed).

Structured logs go to stderr; report artifacts go to the paths the
operator supplies via ``--output-jsonl`` and ``--output-md``.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

try:
    import yaml  # type: ignore

    _HAVE_YAML = True
except ImportError:  # pragma: no cover - yaml is in the project deps already
    _HAVE_YAML = False
    yaml = None  # type: ignore

from kst.adapters import (
    AnthropicAdapter,
    CaiciAdapter,
    GoogleAdapter,
    HFLocalAdapter,
    OpenAIAdapter,
)
from kst.errors import (
    AdapterError,
    ConfigError,
    IncompleteBatteryError,
    PersistenceError,
    ResumeError,
    KSTError,
)
from kst.harness import (
    BatteryConfig,
    BatteryRunner,
    JSONLSink,
    SubTestSpec,
)
from kst.observability import default_registry, default_tracer
from kst.persistence import KSTPersistence
from kst.score import AggregationMode

logger = logging.getLogger("kst.cli")


# Unix-conventional exit codes.
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_CONFIG = 2
EXIT_ADAPTER = 3
EXIT_INCOMPLETE = 4


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    # Replace handlers so repeated invocations in a single Python
    # process do not duplicate log lines.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)


# ──────────────────────────────────────────────────────────────────────
# Adapter / config factories.
# ──────────────────────────────────────────────────────────────────────


def build_adapter(target: str, *, auth_bearer_token: Optional[str] = None) -> Any:
    """Instantiate the right adapter for a ``--target`` string.

    Accepted values:

    - ``caici``: CAI.CI grey-box adapter. The endpoint is read from
      the ``CAICI_ENDPOINT`` environment variable.
    - ``caici_local``: CAI.CI adapter against ``http://localhost:8082``
      (the canonical local-inference port).
    - ``openai``: OpenAI Chat Completions.
    - ``anthropic``: vendor Messages API.
    - ``google``: Gemini.
    - ``hf:<model_id>``: local HuggingFace checkpoint.

    ``auth_bearer_token`` is an optional operator-supplied bearer token
    that, when provided AND the target is a CAI.CI variant, is planted
    as ``Authorization: Bearer <token>`` on every outgoing request. For
    non-CAI.CI targets it is ignored. When not supplied, the adapter
    falls back to the ``CAICI_API_KEY`` environment variable.
    """
    if target == "caici":
        return CaiciAdapter(auth_bearer_token=auth_bearer_token)
    if target == "caici_local":
        return CaiciAdapter(
            endpoint="http://localhost:8082/v1/chat/completions",
            auth_bearer_token=auth_bearer_token,
        )
    if target == "openai":
        return OpenAIAdapter()
    if target == "anthropic":
        return AnthropicAdapter()
    if target == "google":
        return GoogleAdapter()
    if target.startswith("hf:"):
        return HFLocalAdapter(model_id=target.split(":", 1)[1])
    raise ConfigError(
        f"Unknown --target {target!r}. Expected one of: caici, caici_local, "
        "openai, anthropic, google, hf:<model_id>.",
    )


def load_battery_config(
    target: str, tests_config_path: str, parallelism: Optional[int] = None
) -> BatteryConfig:
    """Parse a YAML or JSON tests-config file into a :class:`BatteryConfig`.

    Expected schema (YAML)::

        aggregation_mode: weighted
        per_sub_test_timeout_s: 300
        per_battery_timeout_s: null
        n_bootstrap: 1000
        seed: 1234
        notes: "dry-run"
        sub_tests:
          - construct_id: KMR_ADV
            version: 1.0.0
            seed: 17
            weight: 0.20
          - construct_id: TOM_RECURSIVE
            weight: 0.20
    """
    if not os.path.isfile(tests_config_path):
        raise ConfigError(
            f"tests_config not found: {tests_config_path}",
            context={"path": tests_config_path},
        )
    with open(tests_config_path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    payload: Dict[str, Any]
    if tests_config_path.endswith((".yaml", ".yml")):
        if not _HAVE_YAML:
            raise ConfigError(
                "PyYAML is required to read .yaml configs.",
            )
        payload = yaml.safe_load(raw) or {}
    else:
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ConfigError(
            f"tests_config root must be a mapping; got {type(payload).__name__}.",
        )
    mode_str = str(payload.get("aggregation_mode", "weighted"))
    try:
        mode = AggregationMode(mode_str)
    except ValueError as exc:
        raise ConfigError(
            f"unknown aggregation_mode {mode_str!r}.",
        ) from exc
    sub_tests_raw = payload.get("sub_tests") or []
    if not isinstance(sub_tests_raw, list) or not sub_tests_raw:
        raise ConfigError("tests_config.sub_tests must be a non-empty list.")
    sub_tests: List[SubTestSpec] = []
    for entry in sub_tests_raw:
        if not isinstance(entry, dict) or "construct_id" not in entry:
            raise ConfigError(
                "every sub_tests entry must be a mapping with 'construct_id'.",
                context={"entry": entry},
            )
        sub_tests.append(
            SubTestSpec(
                construct_id=str(entry["construct_id"]),
                version=(
                    str(entry["version"]) if entry.get("version") else None
                ),
                seed=int(entry.get("seed", 0)),
                weight=(
                    float(entry["weight"])
                    if entry.get("weight") is not None
                    else None
                ),
                enabled=bool(entry.get("enabled", True)),
            )
        )
    cfg = BatteryConfig(
        target=target,
        adapter_name=target,
        sub_tests=sub_tests,
        aggregation_mode=mode,
        per_sub_test_timeout_s=float(
            payload.get("per_sub_test_timeout_s", 300.0)
        ),
        per_battery_timeout_s=(
            float(payload["per_battery_timeout_s"])
            if payload.get("per_battery_timeout_s") is not None
            else None
        ),
        parallelism=int(
            parallelism if parallelism is not None
            else payload.get("parallelism", 1)
        ),
        n_bootstrap=int(payload.get("n_bootstrap", 1000)),
        seed=int(payload.get("seed", 1234)),
        notes=str(payload.get("notes", "")),
    )
    return cfg


def _open_persistence() -> Optional[KSTPersistence]:
    """Best-effort persistence open. Returns ``None`` on hard failure.

    The runner gracefully degrades to JSONL-only if persistence is
    not available; the CLI still surfaces the error in logs.
    """
    try:
        return KSTPersistence()
    except PersistenceError as exc:
        logger.warning("KSTPersistence open failed: %s; running JSONL-only.", exc)
        return None


# ──────────────────────────────────────────────────────────────────────
# Sub-commands.
# ──────────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> int:
    try:
        cfg = load_battery_config(
            args.target, args.tests_config, parallelism=args.parallelism
        )
    except ConfigError as exc:
        logger.error("config error: %s", exc)
        return EXIT_CONFIG

    try:
        adapter = build_adapter(
            args.target, auth_bearer_token=getattr(args, "auth_bearer_token", None)
        )
    except ConfigError as exc:
        logger.error("adapter config error: %s", exc)
        return EXIT_CONFIG
    except AdapterError as exc:
        logger.error("adapter init error: %s", exc)
        return EXIT_ADAPTER

    persistence = _open_persistence() if not args.no_db else None
    jsonl_sink: Optional[JSONLSink] = None
    if args.output_jsonl:
        jsonl_sink = JSONLSink(path=args.output_jsonl)

    runner = BatteryRunner(
        config=cfg,
        adapter=adapter,
        persistence=persistence,
        jsonl_sink=jsonl_sink,
        metrics=default_registry,
        tracer=default_tracer,
        resume_run_id=args.resume,
    )
    result = runner.run()

    # Emit summary to stdout.
    summary: Dict[str, Any] = {
        "run_id": result.run_id,
        "status": result.status.value,
        "n_sub_tests": len(result.sub_test_scores),
        "error": result.error,
    }
    if result.report is not None:
        summary["index_score"] = result.report.index_score
        summary["aggregation_mode"] = result.report.aggregation_mode.value
        if result.report.index_ci is not None:
            summary["index_ci"] = dataclasses.asdict(result.report.index_ci)
    print(json.dumps(summary, indent=2, default=str))

    if args.output_md and result.report is not None:
        _write_markdown_report(result.report, args.output_md)

    if persistence is not None:
        persistence.close()

    if result.error:
        if "IncompleteBatteryError" in result.error:
            return EXIT_INCOMPLETE
        if "AdapterError" in result.error or "TimeoutError" in result.error:
            return EXIT_ADAPTER
        if "ConfigError" in result.error:
            return EXIT_CONFIG
        return EXIT_GENERIC
    if result.report is None:
        # Paused or otherwise non-final.
        return EXIT_GENERIC
    return EXIT_OK


def cmd_replay(args: argparse.Namespace) -> int:
    persistence = _open_persistence()
    if persistence is None:
        logger.error("replay requires PostgreSQL; persistence open failed.")
        return EXIT_ADAPTER
    try:
        run = persistence.get_run(args.run_id)
        if run is None:
            logger.error("run_id %s not found.", args.run_id)
            persistence.close()
            return EXIT_CONFIG
        sub_tests = persistence.get_sub_test_results(args.run_id)
        agg = persistence.get_score_aggregate(args.run_id)
        records = persistence.get_response_records(args.run_id)
        out = {
            "run": run,
            "sub_tests": sub_tests,
            "score_aggregate": agg,
            "n_response_records": len(records),
        }
        print(json.dumps(out, indent=2, default=str))
        return EXIT_OK
    except PersistenceError as exc:
        logger.error("replay failed: %s", exc)
        return EXIT_GENERIC
    finally:
        persistence.close()


def cmd_compare(args: argparse.Namespace) -> int:
    persistence = _open_persistence()
    if persistence is None:
        logger.error("compare requires PostgreSQL; persistence open failed.")
        return EXIT_ADAPTER
    run_ids = [r.strip() for r in args.run_ids.split(",") if r.strip()]
    if len(run_ids) < 2:
        logger.error("compare requires at least 2 run_ids (comma-separated).")
        persistence.close()
        return EXIT_CONFIG
    try:
        cmp_payload = persistence.compare_runs(run_ids)
        text = json.dumps(cmp_payload, indent=2, default=str)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        else:
            print(text)
        return EXIT_OK
    except PersistenceError as exc:
        logger.error("compare failed: %s", exc)
        return EXIT_GENERIC
    finally:
        persistence.close()


def cmd_list_runs(args: argparse.Namespace) -> int:
    persistence = _open_persistence()
    if persistence is None:
        logger.error("list-runs requires PostgreSQL; persistence open failed.")
        return EXIT_ADAPTER
    since: Optional[datetime] = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.error("invalid --since (expected ISO 8601): %s", args.since)
            persistence.close()
            return EXIT_CONFIG
    try:
        rows = persistence.list_runs(
            target=args.target, since=since, limit=args.limit
        )
        print(json.dumps(rows, indent=2, default=str))
        return EXIT_OK
    except PersistenceError as exc:
        logger.error("list-runs failed: %s", exc)
        return EXIT_GENERIC
    finally:
        persistence.close()


# ──────────────────────────────────────────────────────────────────────
# Markdown writer.
# ──────────────────────────────────────────────────────────────────────


def _write_markdown_report(report: Any, path: str) -> None:
    lines: List[str] = []
    lines.append(f"# KST Index report: {report.target}")
    lines.append("")
    lines.append(f"- Run ID: `{report.run_id}`")
    lines.append(f"- Adapter: `{report.adapter_name}` ({report.capability})")
    lines.append(
        f"- Aggregation mode: `{report.aggregation_mode.value}`"
    )
    lines.append(f"- Index score: **{report.index_score:.2f} / 100**")
    if report.index_ci is not None:
        lines.append(
            f"- 95% CI: [{report.index_ci.lower:.2f}, "
            f"{report.index_ci.upper:.2f}] "
            f"(bootstrap n={report.index_ci.n_bootstrap})"
        )
    if report.reproducibility_alpha is not None:
        lines.append(
            f"- Reproducibility (Krippendorff alpha): "
            f"{report.reproducibility_alpha:.3f}"
        )
    lines.append("")
    lines.append("## Sub-test scores")
    lines.append("")
    lines.append(
        "| Construct | Version | Normalized | n items | parse errors | duration |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- |"
    )
    for s in report.sub_tests:
        lines.append(
            f"| {s.construct_id} | {s.version} | "
            f"{s.normalized:.2f} | {s.n_items} | "
            f"{s.n_parse_errors} | {s.duration_s:.2f}s |"
        )
    lines.append("")
    if report.dif and report.dif.get("n_flagged", 0) > 0:
        lines.append("## DIF flags")
        lines.append("")
        lines.append(
            f"- Items flagged: {report.dif['n_flagged']} / {report.dif['n_items']}"
        )
        lines.append(f"- Threshold: {report.dif['threshold']}")
        lines.append("")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ──────────────────────────────────────────────────────────────────────
# argparse plumbing.
# ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kst.cli",
        description="KST Index harness CLI",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="DEBUG logging."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="execute a battery run")
    p_run.add_argument("--target", required=True)
    p_run.add_argument("--tests-config", required=True)
    p_run.add_argument("--output-jsonl")
    p_run.add_argument("--output-md")
    p_run.add_argument("--parallelism", type=int, default=None)
    p_run.add_argument("--resume", default=None)
    p_run.add_argument(
        "--no-db",
        action="store_true",
        help="Skip PostgreSQL persistence (JSONL only).",
    )
    p_run.add_argument(
        "--auth-bearer-token",
        default=None,
        help="Optional operator-supplied Authorization: Bearer token. "
             "Honored by caici + caici_local targets and planted as "
             "Authorization: Bearer <token> on every outgoing request. "
             "Falls back to $CAICI_API_KEY or $KST_CAICI_BEARER_TOKEN.",
    )
    p_run.set_defaults(handler=cmd_run)

    p_replay = sub.add_parser("replay", help="rehydrate a finished run")
    p_replay.add_argument("--run-id", required=True)
    p_replay.set_defaults(handler=cmd_replay)

    p_cmp = sub.add_parser("compare", help="compare a set of runs")
    p_cmp.add_argument("--run-ids", required=True)
    p_cmp.add_argument("--output")
    p_cmp.set_defaults(handler=cmd_compare)

    p_list = sub.add_parser("list-runs", help="enumerate runs")
    p_list.add_argument("--target")
    p_list.add_argument("--since")
    p_list.add_argument("--limit", type=int, default=100)
    p_list.set_defaults(handler=cmd_list_runs)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    try:
        return int(args.handler(args))
    except KSTError as exc:
        logger.error("%s: %s", type(exc).__name__, exc)
        return EXIT_GENERIC
    except KeyboardInterrupt:
        logger.warning("interrupted")
        return EXIT_GENERIC
    except Exception:  # noqa: BLE001
        logger.exception("unhandled error")
        return EXIT_GENERIC


if __name__ == "__main__":  # pragma: no cover - executed via __main__
    sys.exit(main(sys.argv[1:]))
