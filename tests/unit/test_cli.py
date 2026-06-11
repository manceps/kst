"""Unit tests for kst.cli.

Cover argparse wiring, exit-code mapping, config loader validation,
and build_adapter target resolution. The ``run`` end-to-end path is
covered separately by the harness unit tests.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from kst.adapters import (
    AnthropicAdapter,
    CaiciAdapter,
    GoogleAdapter,
    HFLocalAdapter,
    OpenAIAdapter,
)
from kst.cli import (
    EXIT_CONFIG,
    EXIT_OK,
    build_adapter,
    build_parser,
    load_battery_config,
)
from kst.errors import ConfigError
from kst.score import AggregationMode


def test_build_parser_recognises_subcommands():
    parser = build_parser()
    args = parser.parse_args(
        ["run", "--target", "caici", "--tests-config", "x.yaml"]
    )
    assert args.cmd == "run"
    assert args.target == "caici"


def test_build_adapter_caici_returns_grey_box():
    a = build_adapter("caici")
    assert isinstance(a, CaiciAdapter)


def test_build_adapter_caici_local_disables_firebase():
    a = build_adapter("caici_local")
    assert isinstance(a, CaiciAdapter)
    assert a.firebase_api_key is None


def test_build_adapter_openai_anthropic_google():
    assert isinstance(build_adapter("openai"), OpenAIAdapter)
    assert isinstance(build_adapter("anthropic"), AnthropicAdapter)
    assert isinstance(build_adapter("google"), GoogleAdapter)


def test_build_adapter_hf_with_model_id():
    a = build_adapter("hf:Qwen/Qwen3-0.6B")
    assert isinstance(a, HFLocalAdapter)
    assert a.model_id == "Qwen/Qwen3-0.6B"


def test_build_adapter_unknown_raises_config_error():
    with pytest.raises(ConfigError):
        build_adapter("totally-unknown")


def test_load_battery_config_yaml(tmp_path):
    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        """
aggregation_mode: arithmetic
per_sub_test_timeout_s: 120.0
n_bootstrap: 500
seed: 7
sub_tests:
  - construct_id: A
    seed: 17
    weight: 0.5
  - construct_id: B
    seed: 18
    weight: 0.5
"""
    )
    cfg = load_battery_config("caici", str(cfg_path))
    assert cfg.aggregation_mode == AggregationMode.ARITHMETIC
    assert cfg.per_sub_test_timeout_s == 120.0
    assert cfg.n_bootstrap == 500
    assert len(cfg.sub_tests) == 2
    assert cfg.sub_tests[0].construct_id == "A"


def test_load_battery_config_json(tmp_path):
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(
        json.dumps(
            {
                "aggregation_mode": "weighted",
                "sub_tests": [
                    {"construct_id": "X", "weight": 0.7},
                    {"construct_id": "Y", "weight": 0.3},
                ],
            }
        )
    )
    cfg = load_battery_config("caici", str(cfg_path))
    assert cfg.aggregation_mode == AggregationMode.WEIGHTED
    assert cfg.sub_tests[0].weight == 0.7


def test_load_battery_config_unknown_aggregation_raises(tmp_path):
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(
        json.dumps(
            {
                "aggregation_mode": "harmonic",
                "sub_tests": [{"construct_id": "A"}],
            }
        )
    )
    with pytest.raises(ConfigError):
        load_battery_config("caici", str(cfg_path))


def test_load_battery_config_empty_sub_tests_raises(tmp_path):
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(json.dumps({"sub_tests": []}))
    with pytest.raises(ConfigError):
        load_battery_config("caici", str(cfg_path))


def test_load_battery_config_missing_file_raises():
    with pytest.raises(ConfigError):
        load_battery_config("caici", "/tmp/nope_does_not_exist.yaml")


def test_load_battery_config_rejects_non_mapping_root(tmp_path):
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(ConfigError):
        load_battery_config("caici", str(cfg_path))


def test_load_battery_config_rejects_entry_missing_construct_id(tmp_path):
    cfg_path = tmp_path / "tests.json"
    cfg_path.write_text(
        json.dumps({"sub_tests": [{"weight": 1.0}]})
    )
    with pytest.raises(ConfigError):
        load_battery_config("caici", str(cfg_path))
