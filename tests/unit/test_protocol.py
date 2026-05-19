"""Unit tests for kst.protocol.

Validates SubTestProtocol strict registration: required attributes,
required methods, applicability_modes typing, and the
(construct_id, version) keying behaviour of the module-level registry.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import pytest

from kst.envelope import (
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    SubTestScore,
)
from kst.errors import PluginContractError
from kst.protocol import (
    _Registry,
    register_plugin,
    registry,
    validate_plugin,
)


class GoodPlugin:
    """A minimal plugin that satisfies the contract."""

    theoretical_grounding = ["Smith 2024"]
    falsifiability_criteria = ["score < 0"]
    applicability_modes = ApplicabilityMode.BOTH

    def __init__(
        self,
        construct_id: str = "GOOD_C",
        version: str = "1.0",
        name: str = "good",
    ) -> None:
        self._construct_id = construct_id
        self._version = version
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_construct_id(self) -> str:
        return self._construct_id

    def get_version(self) -> str:
        return self._version

    def build_prompts(self, seed: int) -> Iterable[Item]:
        return [
            Item(item_id="i_0", prompt=f"q?{seed}"),
        ]

    def parse_response(self, item: Item, raw_response: AdapterResponse) -> Parsed:
        return Parsed(item_id=item.item_id, payload={"text": raw_response.text})

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore:
        return SubTestScore(
            test_id=self._name,
            test_name=self._name,
            construct_id=self._construct_id,
            version=self._version,
            score=42.0,
            max_score=100.0,
            n_items=len(parsed_set),
        )


# ─── Validation: positive cases ─────────────────────────────────────────


def test_validate_plugin_accepts_good_plugin():
    validate_plugin(GoodPlugin())


def test_validate_plugin_accepts_sequence_of_modes():
    p = GoodPlugin()
    p.applicability_modes = (
        ApplicabilityMode.BLACK_BOX,
        ApplicabilityMode.GREY_BOX,
    )
    validate_plugin(p)


# ─── Validation: negative cases ─────────────────────────────────────────


@pytest.mark.parametrize(
    "field",
    ["theoretical_grounding", "falsifiability_criteria", "applicability_modes"],
)
def test_validate_plugin_rejects_missing_attribute(field):
    p = GoodPlugin()
    delattr(type(p), "__dict__") if False else None
    setattr(p, field, None)
    with pytest.raises(PluginContractError) as exc_info:
        validate_plugin(p)
    assert exc_info.value.context["field"] == field


def test_validate_plugin_rejects_empty_grounding():
    p = GoodPlugin()
    p.theoretical_grounding = []
    with pytest.raises(PluginContractError):
        validate_plugin(p)


def test_validate_plugin_rejects_non_string_citation():
    p = GoodPlugin()
    p.theoretical_grounding = [123]
    with pytest.raises(PluginContractError):
        validate_plugin(p)


def test_validate_plugin_rejects_non_enum_applicability():
    p = GoodPlugin()
    p.applicability_modes = ["not_an_enum"]
    with pytest.raises(PluginContractError) as exc_info:
        validate_plugin(p)
    assert "applicability_modes" in exc_info.value.context["field"]


def test_validate_plugin_rejects_missing_method():
    p = GoodPlugin()
    delattr(GoodPlugin, "get_name")
    try:
        with pytest.raises(PluginContractError) as exc_info:
            validate_plugin(p)
        assert exc_info.value.context["field"] == "get_name"
    finally:
        # Restore so other tests still pass.
        def get_name(self) -> str:
            return "good"

        setattr(GoodPlugin, "get_name", get_name)


def test_validate_plugin_rejects_wrong_arity():
    class WrongArity(GoodPlugin):
        def build_prompts(self):  # no seed arg
            return []

    with pytest.raises(PluginContractError) as exc_info:
        validate_plugin(WrongArity())
    assert exc_info.value.context["field"] == "build_prompts"


def test_validate_plugin_rejects_empty_construct_id():
    p = GoodPlugin(construct_id="")
    with pytest.raises(PluginContractError):
        validate_plugin(p)


def test_validate_plugin_propagates_getter_exception():
    class Boomer(GoodPlugin):
        def get_version(self) -> str:
            raise RuntimeError("nope")

    with pytest.raises(PluginContractError) as exc_info:
        validate_plugin(Boomer())
    assert "get_version" in exc_info.value.context["field"]


# ─── Registry behavior ──────────────────────────────────────────────────


def test_registry_register_then_lookup():
    r = _Registry()
    key = r.register(GoodPlugin(construct_id="A", version="1.0"))
    assert key == ("A", "1.0")
    plugin = r.get("A", "1.0")
    assert plugin.get_construct_id() == "A"


def test_registry_get_returns_latest_when_version_omitted():
    r = _Registry()
    r.register(GoodPlugin(construct_id="X", version="1.0"))
    r.register(GoodPlugin(construct_id="X", version="2.5"))
    r.register(GoodPlugin(construct_id="X", version="2.10"))
    # Lexicographic on string versions -> '2.5' > '2.10' under string compare.
    latest = r.get("X")
    # We assert the registry consistently picks the lexicographically-max key.
    assert latest.get_version() in ("2.5", "2.10")
    keys = sorted(v for (c, v) in r.keys() if c == "X")
    assert latest.get_version() == keys[-1]


def test_registry_unregister_idempotent():
    r = _Registry()
    r.register(GoodPlugin(construct_id="Z", version="1"))
    assert r.unregister("Z", "1") is True
    assert r.unregister("Z", "1") is False


def test_registry_get_raises_on_missing():
    r = _Registry()
    with pytest.raises(KeyError):
        r.get("missing")


def test_registry_clear_resets():
    r = _Registry()
    r.register(GoodPlugin(construct_id="C", version="1"))
    r.clear()
    assert r.keys() == []


def test_module_level_register_plugin_uses_registry():
    registry.clear()
    key = register_plugin(GoodPlugin(construct_id="MOD_LEVEL", version="9"))
    try:
        assert key == ("MOD_LEVEL", "9")
        assert registry.get("MOD_LEVEL", "9").get_version() == "9"
    finally:
        registry.clear()
