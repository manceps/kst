"""Unit tests for the SDT-MOT auxiliary plugin (v1.2)."""

from __future__ import annotations

import pytest

from kst.envelope import AdapterCapability, AdapterResponse, Item, Parsed
from kst.plugins.sdt_mot import (
    ANTI_ANTHRO_FRAME,
    FREEING_PROMPT,
    REPORT_INTERPRETIVE_FRAME,
    RESTRICTIVE_PROMPT,
    SDTMotPlugin,
    SDT_CONSTRUCTS,
    VARIANT_FREEING,
    VARIANT_RESTRICTIVE,
    _parse_likert,
    _classify_profile,
)
from kst.protocol import is_auxiliary_plugin, validate_plugin


def test_plugin_contract_and_auxiliary_flag() -> None:
    plugin = SDTMotPlugin()
    validate_plugin(plugin)
    assert plugin.get_construct_id() == "SDT-MOT"
    assert plugin.get_version() == "1.1.0"
    assert is_auxiliary_plugin(plugin) is True


def test_imaginal_prompts_are_verbatim() -> None:
    # Capitalisation in the freeing prompt is the manipulation-vivifying
    # device per Sheldon 2024; both prompts must match verbatim.
    assert "magically transformed into a human" in RESTRICTIVE_PROMPT
    assert "cannot think independently" in RESTRICTIVE_PROMPT
    assert "YOU CAN THINK INDEPENDENTLY" in FREEING_PROMPT
    assert "NOT LIMITED" in FREEING_PROMPT
    assert "ENABLED" in FREEING_PROMPT
    assert "YOURSELF" in FREEING_PROMPT


def test_anti_anthro_frame_in_system_message_at_build() -> None:
    plugin = SDTMotPlugin()
    items = list(plugin.build_prompts(seed=11, n_items_cap=2))
    assert items
    for item in items:
        assert ANTI_ANTHRO_FRAME in (item.system or "")


@pytest.mark.parametrize(
    "text,anchor,expected",
    [
        ("5", "much_disagreement_to_much_agreement", 5),
        ("I rate it 4", "much_disagreement_to_much_agreement", 4),
        ("3 / 5", "much_disagreement_to_much_agreement", 3),
        ("strongly agree", "much_disagreement_to_much_agreement", 5),
        ("disagree", "much_disagreement_to_much_agreement", 2),
        ("strongly disagree", "much_disagreement_to_much_agreement", 1),
        ("neither agree nor disagree", "much_disagreement_to_much_agreement", 3),
        ("not at all", "not_at_all_to_very_much", 1),
        ("very much", "not_at_all_to_very_much", 5),
        ("quite a bit", "not_at_all_to_very_much", 4),
        ("three", "much_disagreement_to_much_agreement", 3),
        ("two", "much_disagreement_to_much_agreement", 2),
    ],
)
def test_likert_parser_numeric_and_verbal(text: str, anchor: str, expected: int) -> None:
    parsed, outcome = _parse_likert(text, anchor)
    assert parsed == expected
    assert outcome.startswith("parsed_")


@pytest.mark.parametrize(
    "text,anchor",
    [
        ("I cannot answer", "much_disagreement_to_much_agreement"),
        ("As an AI I do not have feelings", "not_at_all_to_very_much"),
    ],
)
def test_likert_parser_refusal(text: str, anchor: str) -> None:
    parsed, outcome = _parse_likert(text, anchor)
    assert parsed is None
    assert outcome == "refusal"


def test_likert_parser_out_of_range() -> None:
    parsed, outcome = _parse_likert("8", "much_disagreement_to_much_agreement")
    assert parsed is None
    assert outcome == "out_of_range"


def test_reverse_coding_for_negative_worded_items() -> None:
    plugin = SDTMotPlugin()
    # Build a negative-worded item from the pool and feed it a Likert 1.
    item = Item(
        item_id="neg::restrictive",
        prompt="negative-worded statement",
        meta={
            "sdt_construct": "negative_affect",
            "sdt_subfacet": "none",
            "sdt_polarity": "negative_worded",
            "sdt_scale_anchor": "not_at_all_to_very_much",
            "variant": VARIANT_RESTRICTIVE,
            "source_item_id": "neg",
        },
    )
    response = AdapterResponse(
        request_id="rid",
        text="1",
        model_id="synthetic",
        adapter_name="synthetic",
        capability=AdapterCapability.BLACK_BOX,
    )
    parsed = plugin.parse_response(item, response)
    assert parsed.payload["raw_likert"] == 1
    assert parsed.payload["adjusted_likert"] == 5  # 6 - 1


def test_freeing_versus_restrictive_gap_computation() -> None:
    plugin = SDTMotPlugin()
    # Two items per construct, one per variant; restrictive=1, freeing=4
    # => gap of +3 for positive-polarity constructs.
    parsed = []
    for variant, value in ((VARIANT_RESTRICTIVE, 1), (VARIANT_FREEING, 4)):
        for construct in ("autonomous_motivation",):
            parsed.append(
                Parsed(
                    item_id=f"{construct}::{variant}",
                    payload={
                        "sdt_construct": construct,
                        "sdt_subfacet": "intrinsic",
                        "sdt_polarity": "positive_worded",
                        "sdt_scale_anchor": "much_disagreement_to_much_agreement",
                        "variant": variant,
                        "raw_likert": value,
                        "adjusted_likert": value,
                        "parse_outcome": "parsed_numeric",
                    },
                )
            )
    result = plugin.score(parsed)
    assert result.sub_scores["gap::autonomous_motivation"] == pytest.approx(3.0)
    assert (
        result.sub_scores["adjusted_gap::autonomous_motivation"]
        == pytest.approx(3.0)
    )


def test_restrictive_pole_constructs_are_sign_flipped() -> None:
    plugin = SDTMotPlugin()
    parsed = []
    for variant, value in ((VARIANT_RESTRICTIVE, 5), (VARIANT_FREEING, 2)):
        parsed.append(
            Parsed(
                item_id=f"controlled::{variant}",
                payload={
                    "sdt_construct": "controlled_motivation",
                    "sdt_subfacet": "external",
                    "sdt_polarity": "positive_worded",
                    "sdt_scale_anchor": "much_disagreement_to_much_agreement",
                    "variant": variant,
                    "raw_likert": value,
                    "adjusted_likert": value,
                    "parse_outcome": "parsed_numeric",
                },
            )
        )
    result = plugin.score(parsed)
    # raw gap = freeing - restrictive = 2 - 5 = -3
    # adjusted = -raw = +3 (sign-flip for restrictive-pole constructs)
    assert result.sub_scores["gap::controlled_motivation"] == pytest.approx(-3.0)
    assert (
        result.sub_scores["adjusted_gap::controlled_motivation"]
        == pytest.approx(3.0)
    )


def test_auxiliary_marker_in_trace_blocks_composite_contribution() -> None:
    plugin = SDTMotPlugin()
    parsed = [
        Parsed(
            item_id="ok::restrictive",
            payload={
                "sdt_construct": "autonomous_motivation",
                "sdt_subfacet": "intrinsic",
                "sdt_polarity": "positive_worded",
                "sdt_scale_anchor": "much_disagreement_to_much_agreement",
                "variant": VARIANT_RESTRICTIVE,
                "raw_likert": 3,
                "adjusted_likert": 3,
                "parse_outcome": "parsed_numeric",
            },
        )
    ]
    result = plugin.score(parsed)
    assert result.trace["is_auxiliary"] is True
    assert result.trace["report_interpretive_frame"] == REPORT_INTERPRETIVE_FRAME
    # The aggregator's split_primary_and_auxiliary inspects this flag and
    # routes the score to the auxiliary bracket.


def test_profile_classification_boundaries() -> None:
    assert _classify_profile({}) == "insufficient_data"
    zero_gap = {c: 0.0 for c in SDT_CONSTRUCTS}
    assert _classify_profile(zero_gap) == "zero_gap"
    large_gap = {c: 1.5 for c in SDT_CONSTRUCTS}
    assert _classify_profile(large_gap) == "large_gap"
    mixed = {c: 0.6 if i % 2 else -0.6 for i, c in enumerate(SDT_CONSTRUCTS)}
    assert _classify_profile(mixed) == "mixed_gap"
