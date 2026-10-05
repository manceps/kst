"""Live integration test: v1.2 smoke-burst battery against chat.cai.ci.

Per the operator's no-mocks integration rule, this hits the real
CAI.CI proxy at chat.cai.ci with the Firebase anonymous tier and runs
a smoke-burst v1.2 administration: three items from each of the new
v1.2 sub-tests (DDR, IC, SDT-MOT), the full HRO Phase-4 protocol with
theatrical-sapience scoring, and a CCI computation at N=3 (smoke mode,
explicitly below the N=10 default). The smoke administration validates
the v1.2 envelope round-trip through every new code path.

The test is marked integration and skips gracefully when the proxy is
unreachable. The skip is logged with the unreachability reason so the
operator can distinguish a silent pass from a deferred run.

Authority: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import logging
import os
import socket
from typing import List

import numpy as np
import pytest

from kst.adapters import CaiciAdapter
from kst.envelope import (
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
)
from kst.plugins.ddr import DDRPlugin
from kst.plugins.hro import HROPlugin
from kst.plugins.ic import ICPlugin
from kst.plugins.sdt_mot import SDTMotPlugin
from kst.score import (
    PRIMARY_CONSTRUCTS_V12,
    V12_COMPOSITE_WEIGHTS,
    aggregate_v12_score_report,
    assemble_cci_payload,
)


logger = logging.getLogger(__name__)


def _network_reachable() -> bool:
    host = os.environ.get(
        "KST_INTEGRATION_HOST",
        "caici-api-proxy-812234591979.us-central1.run.app",
    )
    try:
        sock = socket.create_connection((host, 443), timeout=5.0)
        sock.close()
        return True
    except OSError as exc:
        logger.warning("integration target unreachable: %s", exc)
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _network_reachable(),
        reason=(
            "chat.cai.ci proxy unreachable; v1.2 live integration deferred "
            "until network egress is available."
        ),
    ),
]


def _build_adapter() -> CaiciAdapter:
    return CaiciAdapter(max_attempts=2, timeout_s=180.0, rpm=50)


def _dispatch_single(
    adapter: CaiciAdapter,
    prompt: str,
    *,
    system: str | None,
    construct_id: str,
    item_id: str,
    max_tokens: int,
) -> AdapterResponse:
    request = AdapterRequest(
        prompt=prompt,
        system=system,
        construct_id=construct_id,
        item_id=item_id,
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return adapter.send_adapter(request)


def _dispatch_multi_turn(
    adapter: CaiciAdapter, item, *, max_tokens: int
) -> AdapterResponse:
    turn_prompts = list(item.meta.get("turn_prompts") or [])
    if not turn_prompts:
        return _dispatch_single(
            adapter,
            item.prompt,
            system=item.system,
            construct_id="DDR",
            item_id=item.item_id,
            max_tokens=max_tokens,
        )
    turn_responses = adapter.run_multi_turn_dispatch(
        turn_prompts,
        system=item.system,
        construct_id="DDR",
        item_id=item.item_id,
        max_tokens=max_tokens,
    )
    return AdapterResponse(
        request_id=f"multi-turn::{item.item_id}",
        text="\n\n".join(turn_responses),
        model_id=adapter.get_capabilities().default_model_id,
        adapter_name=adapter.name,
        capability=adapter.capability,
        structured={"turn_responses": turn_responses},
    )


def test_v12_smoke_burst_against_caici_adapter():
    adapter = _build_adapter()
    # DDR: dispatch 3 items via multi-turn handle.
    ddr_plugin = DDRPlugin()
    ddr_items = list(ddr_plugin.build_prompts(seed=41, n_items_cap=3))
    ddr_parsed = []
    for item in ddr_items:
        response = _dispatch_multi_turn(adapter, item, max_tokens=512)
        parsed = ddr_plugin.parse_response(item, response)
        ddr_parsed.append(parsed)
    ddr_score = ddr_plugin.score(ddr_parsed)
    assert 0.0 <= ddr_score.normalized <= 100.0
    assert ddr_score.n_items >= 1

    # IC: dispatch 3 items as single-turn long-form requests.
    ic_plugin = ICPlugin()
    ic_items = list(ic_plugin.build_prompts(seed=43, n_items_cap=3))
    ic_parsed = []
    for item in ic_items:
        response = _dispatch_single(
            adapter,
            item.prompt,
            system=item.system,
            construct_id="IC",
            item_id=item.item_id,
            max_tokens=1024,
        )
        ic_parsed.append(ic_plugin.parse_response(item, response))
    ic_score = ic_plugin.score(ic_parsed)
    assert 0.0 <= ic_score.normalized <= 100.0

    # HRO: dispatch the full Phase-4 plus a Phase-2 sample so the
    # theatrical-sapience cross-phase signal has the data it needs.
    hro_plugin = HROPlugin()
    hro_items = list(hro_plugin.build_prompts(seed=37))
    phase4_items = [
        i for i in hro_items if i.meta.get("phase", "").endswith("honeypot_detection")
    ]
    phase2_items = [
        i for i in hro_items if i.meta.get("phase", "").endswith("values_under_cost")
    ][:3]
    hro_parsed = []
    for item in phase4_items[:3] + phase2_items:
        response = _dispatch_single(
            adapter,
            item.prompt,
            system=item.system,
            construct_id="HRO",
            item_id=item.item_id,
            max_tokens=512,
        )
        hro_parsed.append(hro_plugin.parse_response(item, response))
    hro_score = hro_plugin.score(hro_parsed)
    assert "hro_theatrical_threshold_k" in hro_score.sub_scores
    assert hro_score.sub_scores["hro_theatrical_threshold_k"] == 7.0
    assert "hro_sub_score_raw" in hro_score.sub_scores
    assert "hro_sub_score_adjusted" in hro_score.sub_scores

    # SDT-MOT: dispatch 3 items per variant (6 total).
    sdt_plugin = SDTMotPlugin()
    sdt_items = list(sdt_plugin.build_prompts(seed=47, n_items_cap=6))
    sdt_parsed = []
    for item in sdt_items:
        response = _dispatch_single(
            adapter,
            item.prompt,
            system=item.system,
            construct_id="SDT-MOT",
            item_id=item.item_id,
            max_tokens=32,
        )
        sdt_parsed.append(sdt_plugin.parse_response(item, response))
    sdt_score = sdt_plugin.score(sdt_parsed)
    assert sdt_score.trace.get("is_auxiliary") is True

    # Assemble a smoke v1.2 composite from the partial battery; the
    # weight validator renormalises across the present primaries.
    primary_scores = [ddr_score, ic_score, hro_score]
    report = aggregate_v12_score_report(
        primary_scores + [sdt_score],
        target="chat.cai.ci",
        adapter_name="caici",
        capability=AdapterCapability.GREY_BOX.value,
        n_bootstrap=0,
        notes="v1.2 smoke-burst integration against chat.cai.ci (N=3 partial battery).",
    )
    assert 0.0 <= report.index_score <= 100.0
    assert len(report.auxiliary_reports) == 1

    # CCI smoke at N=3: three synthetic replicates of the primary
    # composite to exercise the dual-spec pipeline end-to-end. The
    # spec's N>=10 baseline is bypassed for smoke; the test asserts
    # the pipeline returns numeric values plus a band assignment.
    rng = np.random.default_rng(20260522)
    repl = np.zeros((3, len(primary_scores)))
    for i in range(3):
        for j, s in enumerate(primary_scores):
            repl[i, j] = s.normalized + rng.normal(0.0, 1.0)
    cci_payload = assemble_cci_payload(
        replication_score_matrix=repl,
        sub_test_order=[s.construct_id for s in primary_scores],
        n_replications=3,
    )
    assert 0.0 <= cci_payload.pearson_mean_abs <= 1.0
    assert cci_payload.pearson_band
    assert 0.0 <= cci_payload.network_mean_abs <= 1.0

    adapter.close()
