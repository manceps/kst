"""Unit tests for the ``n_items_cap`` smoke-burst knob across plugins.

Each of the five bundled plugins (APE-A, BWD, HRO, KMR-Adv, ROT-5)
exposes a ``build_prompts(seed, *, n_items_cap=None)`` signature. When
``n_items_cap`` is supplied, the plugin emits at most that many items
as a deterministic prefix of its seed-ordered full item stream. The
smoke run is a strict subset of the corresponding full run for the
same seed, which is what makes divergences easy to diagnose.
"""

from __future__ import annotations

import pytest

from kst.plugins.ape_a import APEAPlugin
from kst.plugins.bwd import BWDPlugin
from kst.plugins.hro import HROPlugin
from kst.plugins.kmr_adv import KMRAdvPlugin
from kst.plugins.rot_5 import ROT5Plugin
from kst.protocol import validate_plugin


@pytest.fixture(
    params=[
        APEAPlugin,
        BWDPlugin,
        HROPlugin,
        KMRAdvPlugin,
        ROT5Plugin,
    ]
)
def plugin(request):
    return request.param()


def test_build_prompts_satisfies_validator(plugin):
    """Adding ``n_items_cap`` as a keyword-only kwarg must not break
    the SubTestProtocol validator: ``build_prompts`` is still allowed
    to declare exactly one positional argument besides ``self``.
    """
    validate_plugin(plugin)


def test_build_prompts_default_emits_full_pool(plugin):
    """Omitting ``n_items_cap`` must preserve the v1.0.0 behaviour:
    the plugin emits its full deterministic item pool.
    """
    items = list(plugin.build_prompts(seed=17))
    assert len(items) > 0


def test_build_prompts_with_cap_emits_at_most_cap_items(plugin):
    """An explicit cap reduces the item stream to at most that many
    items.
    """
    items = list(plugin.build_prompts(seed=17, n_items_cap=2))
    assert len(items) <= 2


def test_build_prompts_cap_is_a_deterministic_prefix(plugin):
    """The cap must be a prefix of the full item stream for the same
    seed: the smoke run is a strict subset of the full run.
    """
    full = list(plugin.build_prompts(seed=42))
    capped = list(plugin.build_prompts(seed=42, n_items_cap=2))
    assert len(capped) == min(2, len(full))
    for a, b in zip(capped, full):
        assert a.item_id == b.item_id


def test_build_prompts_cap_zero_emits_nothing(plugin):
    """``n_items_cap=0`` is a valid degenerate cap that emits no items.
    """
    items = list(plugin.build_prompts(seed=0, n_items_cap=0))
    assert items == []


# ─── SubTestSpec plumbing: cap arrives at plugin via harness ───────────


def test_subtest_spec_propagates_cap_through_load_battery_config(tmp_path):
    from kst.cli import load_battery_config

    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "sub_tests:\n"
        "  - construct_id: KMR-Adv\n"
        "    n_items_cap: 3\n"
    )
    cfg = load_battery_config("caici_local", str(cfg_path))
    assert cfg.sub_tests[0].n_items_cap == 3


def test_subtest_spec_n_items_cap_defaults_to_none(tmp_path):
    from kst.cli import load_battery_config

    cfg_path = tmp_path / "tests.yaml"
    cfg_path.write_text(
        "aggregation_mode: arithmetic\n"
        "sub_tests:\n"
        "  - construct_id: KMR-Adv\n"
    )
    cfg = load_battery_config("caici_local", str(cfg_path))
    assert cfg.sub_tests[0].n_items_cap is None
