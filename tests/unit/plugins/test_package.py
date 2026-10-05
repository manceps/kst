"""Tests for the kst.plugins package surface itself."""

from __future__ import annotations

import importlib

import pytest

import kst.plugins as pkg
from kst import list_plugins, registry


def test_lazy_attribute_loads_module():
    # Force a fresh module import so the __getattr__ path is exercised.
    importlib.reload(pkg)
    mod = pkg.ape_a  # triggers __getattr__
    assert hasattr(mod, "APEAPlugin")


def test_lazy_attribute_unknown_raises_attribute_error():
    importlib.reload(pkg)
    with pytest.raises(AttributeError):
        _ = pkg.nonexistent_module


def test_register_all_populates_registry_with_eight_plugins():
    registry.clear()
    pkg.register_all()
    # v1.2 battery: five v1.0 primaries (APE-A, BWD, HRO, KMR-Adv, ROT-5)
    # plus the two v1.2 primaries (DDR, IC) plus the v1.2 auxiliary
    # (SDT-MOT). The list is sorted alphabetically per list_plugins.
    assert list_plugins() == [
        "APE-A", "BWD", "DDR", "HRO", "IC", "KMR-Adv", "ROT-5", "SDT-MOT",
    ]


def test_register_all_is_idempotent():
    registry.clear()
    pkg.register_all()
    pkg.register_all()  # second call must not error
    assert len(registry.keys()) == 8


def test_register_all_partitions_primary_and_auxiliary():
    registry.clear()
    pkg.register_all()
    primary = {p.get_construct_id() for p in registry.primary_plugins()}
    auxiliary = {p.get_construct_id() for p in registry.auxiliary_plugins()}
    assert primary == {"APE-A", "BWD", "DDR", "HRO", "IC", "KMR-Adv", "ROT-5"}
    assert auxiliary == {"SDT-MOT"}
