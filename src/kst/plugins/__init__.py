"""Kari-Sheldon Test sub-test plugin package.

This package contains the seven primary sub-test plugins plus the
SDT-MOT auxiliary plugin that together comprise the v1.2 battery. Each
module exposes a single plugin class that satisfies
:class:`kst.protocol.SubTestProtocol`.

Plugin slugs (lazy-loaded via :func:`__getattr__` to keep import-time
cost cheap and to defer optional dependencies):

- ``kmr_adv`` -> KMR-Adv  (S2 metacognition).
- ``rot_5``   -> ROT-5    (S4 recursive ToM).
- ``bwd``     -> BWD      (S3 practical wisdom).
- ``ape_a``   -> APE-A    (S1 active inference).
- ``hro``     -> HRO      (S6 honest refusal + integrity factor).
- ``ddr``     -> DDR      (S7 dissatisfaction-driven revision, v1.2).
- ``ic``      -> IC       (capstone joint instantiation across S1-S7, v1.2).
- ``sdt_mot`` -> SDT-MOT  (auxiliary self-report measurement, v1.2).

``register_all`` instantiates the full eight-plugin battery (seven
primaries plus the SDT-MOT auxiliary). The aggregator routes auxiliary
plugins to the bracketed report section per the auxiliary flag.

See `docs/PROPOSED_STANDARD.md` for the construct definitions, sub-test
specifications, and the auxiliary handling rules.

Authority: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import importlib
from typing import Any

_LAZY_MODULES = (
    "ape_a",
    "bwd",
    "ddr",
    "hro",
    "ic",
    "kmr_adv",
    "rot_5",
    "sdt_mot",
)


def __getattr__(name: str) -> Any:
    if name in _LAZY_MODULES:
        module = importlib.import_module(f"kst.plugins.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module 'kst.plugins' has no attribute {name!r}")


def register_all() -> None:
    """Register every bundled sub-test plugin with the module registry.

    Registers the five v1.0 plugins plus the three v1.2 additions (DDR,
    IC primary; SDT-MOT auxiliary). The aggregator inspects each
    plugin's auxiliary attribute to route SDT-MOT to the bracketed
    report section per the auxiliary handling rule. Idempotent: re
    registration of the same (construct_id, version) pair is a no-op
    with a logged warning from the registry layer.
    """
    from kst import register_plugin

    from kst.plugins import ape_a, bwd, ddr, hro, ic, kmr_adv, rot_5, sdt_mot

    register_plugin(ape_a.APEAPlugin())
    register_plugin(bwd.BWDPlugin())
    register_plugin(ddr.DDRPlugin())
    register_plugin(hro.HROPlugin())
    register_plugin(ic.ICPlugin())
    register_plugin(kmr_adv.KMRAdvPlugin())
    register_plugin(rot_5.ROT5Plugin())
    register_plugin(sdt_mot.SDTMotPlugin())


__all__ = list(_LAZY_MODULES) + ["register_all"]
