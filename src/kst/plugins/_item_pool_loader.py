"""JSONL anchor-pool loader for v1.2 sub-test plugins.

The five v1.0 plugins (KMR-Adv, ROT-5, BWD, APE-A, HRO) carry their
items in-module as Python data structures because the v1.0 pools were
small and stable. The three v1.2 plugins (DDR, IC, SDT-MOT) load their
anchor items from ``data/item_pool/*_v1.jsonl`` for two reasons: the
items were hand-authored by the Wave-A construct designers as JSONL
artifacts already, and the rater-manual cross-references point to the
JSONL ``item_id`` UUIDs as the canonical identifier.

The loader resolves the file path against a small list of search
locations so the plugin works both in source checkouts and in installed
wheels. The ``data/`` directory is shipped with the source tree and is
also packaged via the ``[tool.setuptools.package-data]`` block in
``pyproject.toml``; the search order tries the installed package
location first, then the source-tree location, then an explicit
override via the ``KST_ITEM_POOL_DIR`` environment variable.

Authority: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _candidate_pool_dirs() -> List[Path]:
    """Search-order list for the item-pool directory."""
    dirs: List[Path] = []
    override = os.environ.get("KST_ITEM_POOL_DIR")
    if override:
        dirs.append(Path(override))
    here = Path(__file__).resolve()
    # Source tree layout: <repo>/src/kst/plugins/_item_pool_loader.py
    # -> <repo>/data/item_pool.
    for parent in here.parents:
        candidate = parent / "data" / "item_pool"
        if candidate.exists():
            dirs.append(candidate)
            break
    # Installed-package layout fallback.
    cwd = Path.cwd() / "data" / "item_pool"
    if cwd.exists():
        dirs.append(cwd)
    return dirs


def load_pool(pool_name: str) -> List[Dict[str, Any]]:
    """Load ``data/item_pool/<pool_name>.jsonl`` as a list of dicts.

    Raises ``FileNotFoundError`` when the pool file cannot be located in
    any search directory. Raises ``ValueError`` when a record fails JSON
    parsing; the offending line number is included in the message so the
    operator can repair the pool file without re-running the harness.
    """
    filename = f"{pool_name}.jsonl"
    last_err: Exception | None = None
    for base in _candidate_pool_dirs():
        candidate = base / filename
        if not candidate.exists():
            continue
        records: List[Dict[str, Any]] = []
        with candidate.open("r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    records.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{candidate}:{line_no}: invalid JSON: {exc.msg}"
                    ) from exc
        return records
    raise FileNotFoundError(
        f"item pool '{pool_name}' not found in any of: "
        f"{[str(d) for d in _candidate_pool_dirs()]}"
    )


__all__ = ["load_pool"]
