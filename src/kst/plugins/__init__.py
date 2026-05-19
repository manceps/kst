"""KST Index v1.0 sub-test plugin package.

This package contains the five sub-test plugins required for the KST
Index composite. Each module exposes a single plugin class that
satisfies :class:`kst.protocol.SubTestProtocol`.

Plugin slugs (lazy-loaded via :func:`__getattr__` to keep import-time
cost cheap and to defer optional dependencies):

- ``kmr_adv`` -> KMR-Adv  (S2 metacognition).
- ``rot_5``   -> ROT-5    (S4 recursive ToM).
- ``bwd``     -> BWD      (S3 practical wisdom).
- ``ape_a``   -> APE-A    (S1 active inference).
- ``hro``     -> HRO      (S6 honest refusal + integrity factor).

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import importlib
from typing import Any

_LAZY_MODULES = ("ape_a", "bwd", "hro", "kmr_adv", "rot_5")


def __getattr__(name: str) -> Any:
    if name in _LAZY_MODULES:
        module = importlib.import_module(f"kst.plugins.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module 'kst.plugins' has no attribute {name!r}")


def register_all() -> None:
    """Register all five sub-test plugins with the module registry.

    Idempotent: re-registration of the same (construct_id, version)
    pair is a no-op with a logged warning from the registry layer.
    """
    from kst import register_plugin

    from kst.plugins import ape_a, bwd, hro, kmr_adv, rot_5

    register_plugin(ape_a.APEAPlugin())
    register_plugin(bwd.BWDPlugin())
    register_plugin(hro.HROPlugin())
    register_plugin(kmr_adv.KMRAdvPlugin())
    register_plugin(rot_5.ROT5Plugin())


__all__ = list(_LAZY_MODULES) + ["register_all"]
