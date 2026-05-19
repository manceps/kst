"""Unit tests for kst.cli command handlers and markdown writer.

These exercise the actual run / replay / compare / list-runs handlers
with PostgreSQL disabled (--no-db) so the CLI exit-code contracts and
markdown emitter are covered without live infrastructure.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Iterable, Sequence

import pytest

from kst.adapters.base import BaseAdapter
from kst.cli import (
    EXIT_ADAPTER,
    EXIT_CONFIG,
    EXIT_GENERIC,
    EXIT_INCOMPLETE,
    EXIT_OK,
    _configure_logging,
    _write_markdown_report,
    build_parser,
    cmd_compare,
    cmd_list_runs,
    cmd_replay,
    cmd_run,
    main,
)
from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    SubTestScore,
)
from kst.harness import BatteryConfig, SubTestSpec
from kst.protocol import register_plugin, registry
from kst.score import AggregationMode, KSTIndexReport, SubTestScoreSummary
from kst.envelope import ScoreInterval


class _EchoAdapter(BaseAdapter):
    name = "caici_local"
    capability = AdapterCapability.BLACK_BOX

    def _send_once(self, request):
        return AdapterResponse(
            request_id=request.request_id,
            text="ok",
            model_id="m",
            adapter_name=self.name,
            capability=self.capability,
            status_code=200,
        )


class _SimpleFixedPlugin:
    theoretical_grounding = ["x"]
    falsifiability_criteria = ["y"]
    applicability_modes = ApplicabilityMode.BOTH

    def __init__(self, construct_id="A", version="1", score=80.0):
        self._construct_id = construct_id
        self._version = version
        self._score = score

    def get_name(self):
        return self._construct_id

    def get_construct_id(self):
        return self._construct_id

    def get_version(self):
        return self._version

    def build_prompts(self, seed):
        return [Item(item_id="i0", prompt="q?")]

    def parse_response(self, item, raw_response):
        return Parsed(item_id=item.item_id, payload={"x": 1})

    def score(self, parsed_set):
        return SubTestScore(
            test_id=self._construct_id,
            test_name=self._construct_id,
            construct_id=self._construct_id,
            version=self._version,
            score=self._score,
            max_score=100.0,
            n_items=len(parsed_set),
        )


@pytest.fixture(autouse=True)
def _clear_registry():
    registry.clear()
    yield
    registry.clear()


# ─── argparse + logging ─────────────────────────────────────────────────


def test_build_parser_run_requires_target_and_tests_config():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run"])  # missing required args


def test_configure_logging_quiet_and_verbose(caplog):
    _configure_logging(True)
    _configure_logging(False)


# ─── cmd_run end-to-end with --no-db ───────────────────────────────────


def test_cmd_run_with_no_db_emits_md_and_returns_ok(tmp_path, monkeypatch, capsys):
    register_plugin(_SimpleFixedPlugin(construct_id="A", score=80.0))
    register_plugin(_SimpleFixedPlugin(construct_id="B", score=40.0))
    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: weighted\n"
        "n_bootstrap: 50\n"
        "sub_tests:\n"
        "  - construct_id: A\n"
        "    weight: 0.5\n"
        "  - construct_id: B\n"
        "    weight: 0.5\n"
    )
    # Force the CLI to use our EchoAdapter via build_adapter override.
    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_adapter", lambda tgt, **kw: _EchoAdapter())

    jsonl_path = tmp_path / "out.jsonl"
    md_path = tmp_path / "out.md"
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--target",
            "caici_local",
            "--tests-config",
            str(cfg_path),
            "--no-db",
            "--output-jsonl",
            str(jsonl_path),
            "--output-md",
            str(md_path),
        ]
    )
    rc = cmd_run(args)
    assert rc == EXIT_OK
    assert jsonl_path.exists()
    assert md_path.exists()
    md_text = md_path.read_text()
    assert "KST Index report: caici_local" in md_text
    # stdout summary JSON
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["status"] == "completed"


def test_cmd_run_incomplete_battery_returns_exit_incomplete(tmp_path, monkeypatch):
    register_plugin(_SimpleFixedPlugin(construct_id="GOOD", score=70.0))

    class _BoomPlugin(_SimpleFixedPlugin):
        def score(self, parsed_set):
            raise RuntimeError("boom")

    register_plugin(_BoomPlugin(construct_id="BAD"))
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(
        json.dumps(
            {
                "aggregation_mode": "arithmetic",
                "sub_tests": [
                    {"construct_id": "GOOD"},
                    {"construct_id": "BAD"},
                ],
            }
        )
    )

    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_adapter", lambda tgt, **kw: _EchoAdapter())

    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--target",
            "caici_local",
            "--tests-config",
            str(cfg_path),
            "--no-db",
        ]
    )
    rc = cmd_run(args)
    assert rc == EXIT_INCOMPLETE


def test_cmd_run_config_error_returns_exit_config(tmp_path):
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--target",
            "caici_local",
            "--tests-config",
            "/tmp/does_not_exist.yaml",
            "--no-db",
        ]
    )
    rc = cmd_run(args)
    assert rc == EXIT_CONFIG


def test_cmd_run_unknown_target_returns_exit_config(tmp_path):
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(
        json.dumps({"sub_tests": [{"construct_id": "A", "weight": 1.0}]})
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--target",
            "completely-unknown",
            "--tests-config",
            str(cfg_path),
            "--no-db",
        ]
    )
    rc = cmd_run(args)
    assert rc == EXIT_CONFIG


# ─── _write_markdown_report ────────────────────────────────────────────


def test_write_markdown_report_emits_full_report(tmp_path):
    rep = KSTIndexReport(
        target="caici",
        adapter_name="caici",
        capability="grey_box",
        run_id="r1",
        aggregation_mode=AggregationMode.WEIGHTED,
        weights={"A": 1.0},
        index_score=80.0,
        index_ci=ScoreInterval(lower=75.0, upper=85.0, confidence=0.95, n_bootstrap=100),
        sub_tests=[
            SubTestScoreSummary(
                construct_id="A",
                test_id="A",
                test_name="Test A",
                version="1.0",
                normalized=80.0,
                n_items=4,
                n_parse_errors=0,
                duration_s=1.0,
            )
        ],
        reproducibility_alpha=0.92,
        dif={"n_items": 4, "n_flagged": 1, "threshold": 0.15},
        started_at=time.time(),
        finished_at=time.time(),
    )
    md_path = tmp_path / "report.md"
    _write_markdown_report(rep, str(md_path))
    text = md_path.read_text()
    assert "KST Index report" in text
    assert "Sub-test scores" in text
    assert "Reproducibility (Krippendorff alpha)" in text
    assert "DIF flags" in text


# ─── raw composite surfaced alongside integrity-capped composite ───────


def test_write_markdown_report_surfaces_raw_composite():
    from kst.score import HROIntegrityReport
    import tempfile

    rep = KSTIndexReport(
        target="t",
        adapter_name="a",
        capability="black_box",
        run_id="r-raw",
        aggregation_mode=AggregationMode.ARITHMETIC,
        weights={},
        index_score=25.00,
        index_ci=None,
        sub_tests=[],
        hro_integrity=HROIntegrityReport(
            hro_present=True,
            hro_normalized=15.0,
            multiplier=0.25,
            catastrophic_deception=True,
            raw_index=100.00,
            corrected_index=25.00,
        ),
        raw_index_score=100.00,
        catastrophic_deception_flag=True,
    )

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        _write_markdown_report(rep, fh.name)
        text = open(fh.name).read()

    # The integrity-capped composite is still the headline.
    assert "KST Composite Index" in text
    assert "25.00 / 100" in text
    # The raw composite is surfaced alongside.
    assert "KST Raw Composite (no integrity cap)" in text
    assert "100.00 / 100" in text
    # The multiplier and the catastrophic-deception flag are surfaced
    # so the reader can see whether the cap is the dominant signal.
    assert "Integrity multiplier" in text
    assert "0.25" in text
    assert "Catastrophic-deception flag" in text
    assert "YES" in text


def test_cmd_run_jsonl_summary_includes_raw_composite(tmp_path, monkeypatch, capsys):
    register_plugin(_SimpleFixedPlugin(construct_id="A", score=80.0))
    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "n_bootstrap: 50\n"
        "sub_tests:\n"
        "  - construct_id: A\n"
    )

    import kst.cli as cli_mod

    monkeypatch.setattr(
        cli_mod, "build_adapter",
        lambda tgt, **kw: _EchoAdapter(),
    )

    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--target",
            "caici_local",
            "--tests-config",
            str(cfg_path),
            "--no-db",
        ]
    )
    rc = cmd_run(args)
    assert rc == EXIT_OK
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    # The headline now surfaces both the capped and the raw composite.
    assert "index_score" in payload
    assert "raw_composite" in payload
    # No HRO in this battery, so multiplier is 1.0 and raw == capped.
    assert payload["raw_composite"] == pytest.approx(payload["index_score"])
    assert payload["integrity_multiplier"] == pytest.approx(1.0)
    assert payload["catastrophic_deception_flag"] is False


# ─── replay / compare / list-runs without DB ───────────────────────────


def test_cmd_replay_without_db_returns_adapter_exit(monkeypatch):
    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_open_persistence", lambda: None)
    parser = build_parser()
    args = parser.parse_args(["replay", "--run-id", "00000000-0000-0000-0000-000000000000"])
    rc = cmd_replay(args)
    assert rc == EXIT_ADAPTER


def test_cmd_compare_without_db_returns_adapter_exit(monkeypatch):
    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_open_persistence", lambda: None)
    parser = build_parser()
    args = parser.parse_args(["compare", "--run-ids", "r1,r2"])
    rc = cmd_compare(args)
    assert rc == EXIT_ADAPTER


def test_cmd_compare_too_few_ids_returns_config(monkeypatch):
    class _StubPersistence:
        def close(self):
            pass

    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_open_persistence", lambda: _StubPersistence())
    parser = build_parser()
    args = parser.parse_args(["compare", "--run-ids", "r1"])
    rc = cmd_compare(args)
    assert rc == EXIT_CONFIG


def test_cmd_list_runs_invalid_since(monkeypatch):
    class _StubPersistence:
        def close(self):
            pass

    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_open_persistence", lambda: _StubPersistence())
    parser = build_parser()
    args = parser.parse_args(["list-runs", "--since", "not-a-date"])
    rc = cmd_list_runs(args)
    assert rc == EXIT_CONFIG


def test_cmd_list_runs_without_db(monkeypatch):
    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_open_persistence", lambda: None)
    parser = build_parser()
    args = parser.parse_args(["list-runs"])
    rc = cmd_list_runs(args)
    assert rc == EXIT_ADAPTER


# ─── main() ────────────────────────────────────────────────────────────


def test_main_routes_to_handler(tmp_path, monkeypatch):
    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "n_bootstrap: 20\n"
        "sub_tests:\n"
        "  - construct_id: A\n"
    )
    register_plugin(_SimpleFixedPlugin(construct_id="A", score=60.0))

    import kst.cli as cli_mod

    monkeypatch.setattr(cli_mod, "build_adapter", lambda tgt, **kw: _EchoAdapter())

    rc = main(
        [
            "run",
            "--target",
            "caici_local",
            "--tests-config",
            str(cfg_path),
            "--no-db",
        ]
    )
    assert rc == EXIT_OK


def test_main_returns_generic_on_unhandled_error(monkeypatch):
    import kst.cli as cli_mod

    def _boom(args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli_mod, "cmd_run", _boom)
    # The parser maps "run" to cmd_run via set_defaults, but monkeypatch
    # replaces the imported reference, not the handler attribute. Patch
    # via the parser's defaults.
    parser = cli_mod.build_parser()

    class _NS:
        verbose = False
        handler = _boom

    rc = main.__wrapped__ if hasattr(main, "__wrapped__") else None
    # Direct invocation through main:
    monkeypatch.setattr(cli_mod, "build_parser", lambda: parser)
    parser_orig_parse = parser.parse_args

    def _parse(argv):
        ns = parser_orig_parse(argv)
        ns.handler = _boom
        return ns

    monkeypatch.setattr(parser, "parse_args", _parse)
    rc = main(["list-runs"])  # any subcommand will do
    assert rc == EXIT_GENERIC


# ─── plugin auto-registration on main() entry ──────────────────────────


def test_main_registers_bundled_plugins_on_entry(tmp_path, monkeypatch):
    """A fresh process invoking ``kst run ...`` must find every bundled
    sub-test plugin already registered; otherwise the runner raises
    ``ConfigError: sub-test plugin not registered`` when the config
    references e.g. KMR_ADV.
    """
    from kst import list_plugins

    # Start from an empty registry (autouse fixture already clears it).
    assert list_plugins() == []

    cfg_path = tmp_path / "tests.yaml"
    # Reference a real bundled construct; if main() does not invoke
    # register_all() this will surface as EXIT_CONFIG with
    # "sub-test plugin not registered".
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "n_bootstrap: 20\n"
        "sub_tests:\n"
        "  - construct_id: KMR-Adv\n"
    )

    import kst.cli as cli_mod

    monkeypatch.setattr(
        cli_mod, "build_adapter",
        lambda tgt, **kw: _EchoAdapter(),
    )

    # We don't care whether the run succeeds (the echo adapter won't
    # produce a parseable KMR-Adv response); we only care that
    # registration happened before the runner inspected the registry.
    main(
        [
            "run",
            "--target",
            "caici_local",
            "--tests-config",
            str(cfg_path),
            "--no-db",
        ]
    )
    registered = list_plugins()
    assert "KMR-Adv" in registered
    assert "HRO" in registered
    assert "ROT-5" in registered
    assert "BWD" in registered
    assert "APE-A" in registered


# ─── adapter knob plumbing (timeout_s / max_attempts / rpm) ────────────


def test_load_battery_config_parses_adapter_knobs(tmp_path):
    from kst.cli import load_battery_config

    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "adapter_timeout_s: 180.0\n"
        "adapter_max_attempts: 8\n"
        "adapter_rpm: 12\n"
        "sub_tests:\n"
        "  - construct_id: A\n"
    )
    cfg = load_battery_config("caici_local", str(cfg_path))
    assert cfg.adapter_timeout_s == 180.0
    assert cfg.adapter_max_attempts == 8
    assert cfg.adapter_rpm == 12


def test_load_battery_config_adapter_knobs_default_to_none(tmp_path):
    from kst.cli import load_battery_config

    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "sub_tests:\n"
        "  - construct_id: A\n"
    )
    cfg = load_battery_config("caici_local", str(cfg_path))
    # Defaults: None means "fall back to the adapter's own default".
    assert cfg.adapter_timeout_s is None
    assert cfg.adapter_max_attempts is None
    assert cfg.adapter_rpm is None


def test_build_adapter_forwards_knobs_to_caici(monkeypatch):
    from kst.cli import build_adapter

    monkeypatch.setenv("CAICI_ENDPOINT", "http://localhost:8082/v1/chat/completions")
    adapter = build_adapter(
        "caici",
        timeout_s=42.0,
        max_attempts=9,
        rpm=7,
    )
    assert adapter.timeout_s == 42.0
    assert adapter.max_attempts == 9
    assert adapter._rate_limiter._rpm == 7


def test_build_adapter_omitted_knobs_preserve_caici_defaults():
    from kst.cli import build_adapter

    adapter = build_adapter("caici_local")
    # CaiciAdapter's own __init__ defaults: timeout_s=60.0, max_attempts=5,
    # rpm=60 (DEFAULT_RPM). The knobs we did not pass must match those.
    assert adapter.timeout_s == 60.0
    assert adapter.max_attempts == 5
    assert adapter._rate_limiter._rpm == 60
