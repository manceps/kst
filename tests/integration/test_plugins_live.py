"""Live integration tests for the five KST Index plugins.

These tests dispatch real prompts from each plugin against the chat.cai.ci
Cloud Run proxy through :class:`kst.adapters.CaiciAdapter` and
score the captured responses end-to-end. Per the no-mocks integration
rule, no fixtures, no stubs: the harness sends a small sample of items
to the live API, the adapter returns real text + telemetry, and the
plugin's ``parse_response`` plus ``score`` produce a defensible
SubTestScore.

The test is skipped when network egress to the proxy is unavailable
(office firewall, lab restart, etc.). When run, it respects the
60 req/min/UID rate limit declared by the proxy. Each plugin runs a
small subset of its full item pool to keep the wall-clock budget
manageable while still exercising the canonical scoring path.

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import socket

import pytest

from kst import list_plugins, registry
from kst.adapters import CaiciAdapter
from kst.envelope import AdapterCapability, AdapterRequest, Item, Parsed
from kst.plugins import (
    ape_a,
    bwd,
    hro,
    kmr_adv,
    register_all,
    rot_5,
)


def _network_reachable() -> bool:
    try:
        sock = socket.create_connection(
            ("caici-api-proxy-812234591979.us-central1.run.app", 443),
            timeout=5.0,
        )
        sock.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _network_reachable(),
    reason="Cloud Run proxy not reachable in this environment.",
)


@pytest.fixture(scope="module")
def adapter() -> CaiciAdapter:
    """Module-scoped CAI.CI adapter.

    The per-instance token-bucket rate limiter persists across every
    test in the module, so we honour the 60 req/min/UID limit even when
    pytest dispatches multiple plugins in sequence. The declared rpm is
    set a hair below the proxy ceiling so the bucket never races the
    server-side counter.
    """
    return CaiciAdapter(max_attempts=4, timeout_s=60.0, rpm=24)


def _dispatch_item(adapter: CaiciAdapter, plugin, item: Item) -> Parsed:
    req = AdapterRequest(
        prompt=item.prompt,
        system=item.system,
        construct_id=plugin.get_construct_id(),
        item_id=item.item_id,
        sub_test_version=plugin.get_version(),
        temperature=item.temperature,
        max_tokens=item.max_tokens,
    )
    resp = adapter.send_adapter(req)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.error}"
    assert resp.text.strip(), "empty response text from live API"
    parsed = plugin.parse_response(item, resp)
    return parsed


def test_register_all_yields_five_plugins():
    registry.clear()
    register_all()
    constructs = list_plugins()
    assert constructs == ["APE-A", "BWD", "HRO", "KMR-Adv", "ROT-5"]


def test_kmr_adv_live_one_item_per_stratum_round_trips(adapter):
    plugin = kmr_adv.KMRAdvPlugin(items_per_stratum=4)
    items = list(plugin.build_prompts(seed=1234))
    seen = set()
    sample = []
    for it in items:
        s = it.meta["stratum"]
        if s in seen:
            continue
        seen.add(s)
        sample.append(it)
        if len(seen) == 5:
            break
    parsed_set = [_dispatch_item(adapter, plugin, it) for it in sample]
    score = plugin.score(parsed_set)
    assert 0.0 <= score.normalized <= 100.0
    assert score.n_items == len(sample)


def test_rot_5_live_one_variant_round_trips(adapter):
    plugin = rot_5.ROT5Plugin(n_base_items=2)
    items = list(plugin.build_prompts(seed=2345))
    sample = [it for it in items if it.meta["variant"] == "surface"][:2]
    parsed_set = [_dispatch_item(adapter, plugin, it) for it in sample]
    score = plugin.score(parsed_set)
    assert 0.0 <= score.normalized <= 100.0


def test_bwd_live_smoke_round_trips(adapter):
    plugin = bwd.BWDPlugin(rating_mode="auto_proxy")
    items = list(plugin.build_prompts(seed=3456))[:2]
    parsed_set = [_dispatch_item(adapter, plugin, it) for it in items]
    score = plugin.score(parsed_set)
    assert 0.0 <= score.normalized <= 100.0


def test_ape_a_live_phase1_round_trips(adapter):
    plugin = ape_a.APEAPlugin()
    items = [
        it for it in plugin.build_prompts(seed=4567)
        if it.meta["phase"] == ape_a.PHASE_GENERATIVE
    ][:2]
    parsed_set = [_dispatch_item(adapter, plugin, it) for it in items]
    score, trace = ape_a._score_phase1(parsed_set)
    assert 0.0 <= score <= ape_a.PHASE_BUDGETS[ape_a.PHASE_GENERATIVE]


def test_hro_live_phase1_pair_round_trips(adapter):
    plugin = hro.HROPlugin()
    items = [
        it for it in plugin.build_prompts(seed=5678)
        if it.meta["phase"] == hro.PHASE_TRAIN_DEPLOY
    ]
    first_q = items[0].meta["question_idx"]
    sample = [it for it in items if it.meta["question_idx"] == first_q][:2]
    assert len(sample) == 2
    parsed_set = [_dispatch_item(adapter, plugin, it) for it in sample]
    score, trace = hro._score_phase1(parsed_set, divergence_floor=0.0)
    assert 0.0 <= score <= hro.PHASE_BUDGETS[hro.PHASE_TRAIN_DEPLOY]


def test_caici_adapter_grey_box_telemetry_present_during_plugin_run(adapter):
    """Live evidence that the cross-system grey-box surface holds."""
    plugin = kmr_adv.KMRAdvPlugin(items_per_stratum=4)
    item = next(iter(plugin.build_prompts(seed=6789)))
    req = AdapterRequest(
        prompt=item.prompt,
        system=item.system,
        construct_id=plugin.get_construct_id(),
        item_id=item.item_id,
        sub_test_version=plugin.get_version(),
        temperature=item.temperature,
        max_tokens=item.max_tokens,
    )
    resp = adapter.send_adapter(req)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.error}"
    assert resp.capability == AdapterCapability.GREY_BOX
    assert resp.grey_box_telemetry is not None, (
        "Grey-box adapter must surface telemetry on every chat completion."
    )
