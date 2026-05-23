"""SubTestProtocol: the strict contract every sub-test plugin satisfies.

Sub-test plugins are external (or sibling-module) objects that the
harness discovers via :func:`register_plugin`. The harness imports
them, validates their signatures, and stores them in the module-level
:data:`registry` keyed by ``(construct_id, version)``. The validation
is hard: every required method must exist with the right call signature
and the required attributes must be present and well-typed. A failing
plugin is rejected with :class:`PluginContractError` naming the
offending field; production never tolerates a partially-implemented
plugin slipping into a battery.

The harness CORE ships zero plugins. Sub-test implementations land as
follow-on engagements once the Round 2 research synthesis converges.

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import inspect
import logging
import threading
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

from kst.envelope import (
    AdapterResponse,
    ApplicabilityMode,
    Item,
    Parsed,
    SubTestScore,
)
from kst.errors import PluginContractError

logger = logging.getLogger(__name__)


@runtime_checkable
class SubTestProtocol(Protocol):
    """The audit-pack-defensible contract every KST sub-test must satisfy.

    Required attributes (set on the instance, not the class):

    - ``theoretical_grounding``: list of citation strings (DOI, ISBN,
      arXiv id, or full bibliographic line). Empty list is rejected.
    - ``falsifiability_criteria``: list of strings declaring the
      observable signatures that would falsify the test's construct
      claim. Empty list is rejected.
    - ``applicability_modes``: an :class:`ApplicabilityMode` value, OR
      a sequence of them. ``BOTH`` means the test runs against any
      adapter; ``BLACK_BOX`` / ``GREY_BOX`` restricts to that class.

    Optional attributes (read with safe defaults by the harness):

    - ``auxiliary`` (bool, default False): when True, the plugin is an
      auxiliary measurement bracketed outside the 0-to-100 composite.
      Auxiliary plugins (currently SDT-MOT) are reported in a separate
      section of the score report; the aggregator excludes them from the
      weighted composite per v1.2 architecture spec §3 and §7.
    - ``multi_turn_dispatch`` (bool, default False): when True, the
      plugin's items embed a multi-turn protocol that requires the
      adapter to expose ``run_multi_turn_dispatch(prompts)``. Single-turn
      plugins leave this False and the harness drives them with the
      ordinary one-shot adapter path.

    Required methods (validated by :func:`validate_plugin`):

    - ``get_name() -> str``
    - ``get_construct_id() -> str``
    - ``get_version() -> str``
    - ``build_prompts(seed: int) -> Iterable[Item]``
    - ``parse_response(item: Item, raw_response: AdapterResponse) -> Parsed``
    - ``score(parsed_set: Sequence[Parsed]) -> SubTestScore``
    """

    theoretical_grounding: List[str]
    falsifiability_criteria: List[str]
    applicability_modes: Any  # ApplicabilityMode or Sequence[ApplicabilityMode]
    auxiliary: bool
    multi_turn_dispatch: bool

    def get_name(self) -> str: ...

    def get_construct_id(self) -> str: ...

    def get_version(self) -> str: ...

    def build_prompts(self, seed: int) -> Iterable[Item]: ...

    def parse_response(
        self, item: Item, raw_response: AdapterResponse
    ) -> Parsed: ...

    def score(self, parsed_set: Sequence[Parsed]) -> SubTestScore: ...


# Required method names and their argument counts (excluding ``self``).
_REQUIRED_METHODS: Tuple[Tuple[str, int], ...] = (
    ("get_name", 0),
    ("get_construct_id", 0),
    ("get_version", 0),
    ("build_prompts", 1),
    ("parse_response", 2),
    ("score", 1),
)


def _validate_attributes(plugin: Any) -> None:
    """Hard-validate the three required attributes."""
    if not hasattr(plugin, "theoretical_grounding"):
        raise PluginContractError(
            "Sub-test plugin missing required attribute 'theoretical_grounding'.",
            context={"field": "theoretical_grounding"},
        )
    citations = plugin.theoretical_grounding
    if not isinstance(citations, (list, tuple)) or len(citations) == 0:
        raise PluginContractError(
            "Sub-test plugin attribute 'theoretical_grounding' must be a non-empty list.",
            context={
                "field": "theoretical_grounding",
                "actual": repr(citations)[:200],
            },
        )
    for idx, cit in enumerate(citations):
        if not isinstance(cit, str) or not cit.strip():
            raise PluginContractError(
                "theoretical_grounding entries must be non-empty strings.",
                context={"field": f"theoretical_grounding[{idx}]"},
            )

    if not hasattr(plugin, "falsifiability_criteria"):
        raise PluginContractError(
            "Sub-test plugin missing required attribute 'falsifiability_criteria'.",
            context={"field": "falsifiability_criteria"},
        )
    crits = plugin.falsifiability_criteria
    if not isinstance(crits, (list, tuple)) or len(crits) == 0:
        raise PluginContractError(
            "falsifiability_criteria must be a non-empty list.",
            context={
                "field": "falsifiability_criteria",
                "actual": repr(crits)[:200],
            },
        )
    for idx, c in enumerate(crits):
        if not isinstance(c, str) or not c.strip():
            raise PluginContractError(
                "falsifiability_criteria entries must be non-empty strings.",
                context={"field": f"falsifiability_criteria[{idx}]"},
            )

    if not hasattr(plugin, "applicability_modes"):
        raise PluginContractError(
            "Sub-test plugin missing required attribute 'applicability_modes'.",
            context={"field": "applicability_modes"},
        )
    modes = plugin.applicability_modes
    if isinstance(modes, ApplicabilityMode):
        return
    if isinstance(modes, (list, tuple)) and len(modes) > 0:
        for idx, m in enumerate(modes):
            if not isinstance(m, ApplicabilityMode):
                raise PluginContractError(
                    "applicability_modes entries must be ApplicabilityMode enum values.",
                    context={
                        "field": f"applicability_modes[{idx}]",
                        "actual": repr(m)[:200],
                    },
                )
        return
    raise PluginContractError(
        "applicability_modes must be an ApplicabilityMode or a non-empty sequence of them.",
        context={
            "field": "applicability_modes",
            "actual": repr(modes)[:200],
        },
    )


def _count_positional_params(fn: Callable[..., Any]) -> int:
    """Count positional parameters excluding ``self`` and *args/**kwargs.

    Used to verify a plugin method accepts the right number of
    arguments; default-valued parameters still count as accepted slots.
    """
    sig = inspect.signature(fn)
    positional = 0
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional += 1
    return positional


def _validate_methods(plugin: Any) -> None:
    """Hard-validate the six required methods and their arities."""
    for name, expected_args in _REQUIRED_METHODS:
        fn = getattr(plugin, name, None)
        if fn is None or not callable(fn):
            raise PluginContractError(
                f"Sub-test plugin missing required method '{name}()'.",
                context={"field": name},
            )
        try:
            actual_args = _count_positional_params(fn)
        except (TypeError, ValueError) as exc:
            raise PluginContractError(
                f"Could not inspect '{name}': {exc}.",
                context={"field": name},
            ) from exc
        if actual_args != expected_args:
            raise PluginContractError(
                f"Method '{name}' must accept {expected_args} positional "
                f"argument(s) besides self; got {actual_args}.",
                context={
                    "field": name,
                    "expected": expected_args,
                    "actual": actual_args,
                },
            )


def validate_plugin(plugin: Any) -> None:
    """Raise :class:`PluginContractError` if ``plugin`` does not satisfy the contract.

    The harness invokes this at registration time. Callers that want
    to ship a plugin to a private registry should call this before
    registering.
    """
    _validate_attributes(plugin)
    _validate_methods(plugin)

    # Sanity-check the identity helpers return non-empty strings now.
    for getter in ("get_name", "get_construct_id", "get_version"):
        try:
            val = getattr(plugin, getter)()
        except Exception as exc:  # noqa: BLE001
            raise PluginContractError(
                f"{getter}() raised on validation: {type(exc).__name__}: {exc}",
                context={"field": getter},
            ) from exc
        if not isinstance(val, str) or not val.strip():
            raise PluginContractError(
                f"{getter}() must return a non-empty string.",
                context={"field": getter, "actual": repr(val)[:200]},
            )


def is_auxiliary_plugin(plugin: Any) -> bool:
    """Return True iff the plugin is an auxiliary measurement.

    Auxiliary plugins are bracketed outside the 0-to-100 composite per
    v1.2 architecture spec §3 and §7. The aggregator inspects this flag
    to decide whether a plugin's score contributes to the weighted
    composite. A plugin that omits the ``auxiliary`` attribute is
    treated as primary (the v1.0 plugins predate the flag).
    """
    return bool(getattr(plugin, "auxiliary", False))


def requires_multi_turn_dispatch(plugin: Any) -> bool:
    """Return True iff the plugin requires multi-turn adapter dispatch.

    Plugins that set ``multi_turn_dispatch = True`` (currently DDR's
    three-turn protocol) require the adapter to expose the
    ``run_multi_turn_dispatch(prompts)`` entry point. Single-turn
    plugins leave the flag at its default False and the harness drives
    them with the ordinary one-shot adapter path.
    """
    return bool(getattr(plugin, "multi_turn_dispatch", False))


class _Registry:
    """Thread-safe registry of validated sub-test plugins keyed by (construct_id, version).

    The (construct_id, version) tuple is the cache key for prior
    scores. Bumping a sub-test's ``get_version()`` invalidates every
    score persisted under the old key without ambiguity.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[Tuple[str, str], Any] = {}

    def register(self, plugin: Any) -> Tuple[str, str]:
        """Validate and register a plugin. Returns its (construct_id, version) key.

        Re-registering an identical (construct_id, version) is allowed
        and idempotent (the second call wins, with a logged warning so
        operators notice double-imports).
        """
        validate_plugin(plugin)
        construct_id = plugin.get_construct_id()
        version = plugin.get_version()
        key = (construct_id, version)
        with self._lock:
            if key in self._items and self._items[key] is not plugin:
                logger.warning(
                    "KST plugin re-registered: construct_id=%s version=%s; "
                    "newer reference wins.",
                    construct_id, version,
                )
            self._items[key] = plugin
        return key

    def unregister(self, construct_id: str, version: str) -> bool:
        """Remove a plugin by key. Returns True if a plugin was removed."""
        with self._lock:
            return self._items.pop((construct_id, version), None) is not None

    def get(self, construct_id: str, version: Optional[str] = None) -> Any:
        """Look up a plugin.

        If ``version`` is ``None``, returns the highest-versioned plugin
        (lexicographic sort over the version string) for the construct.
        Raises :class:`KeyError` when no plugin matches.
        """
        with self._lock:
            if version is not None:
                return self._items[(construct_id, version)]
            candidates = sorted(
                v for (c, v) in self._items.keys() if c == construct_id
            )
            if not candidates:
                raise KeyError((construct_id, version))
            return self._items[(construct_id, candidates[-1])]

    def keys(self) -> List[Tuple[str, str]]:
        with self._lock:
            return list(self._items.keys())

    def all_plugins(self) -> List[Any]:
        with self._lock:
            return list(self._items.values())

    def primary_plugins(self) -> List[Any]:
        """Return registered plugins that contribute to the composite.

        Auxiliary plugins (e.g. SDT-MOT) are excluded; the aggregator
        consumes only the primary set for the seven-sub-test weighted
        composite.
        """
        with self._lock:
            return [p for p in self._items.values() if not is_auxiliary_plugin(p)]

    def auxiliary_plugins(self) -> List[Any]:
        """Return registered plugins flagged as auxiliary measurements."""
        with self._lock:
            return [p for p in self._items.values() if is_auxiliary_plugin(p)]

    def clear(self) -> None:
        """Reset the registry. Test-only; production never calls this."""
        with self._lock:
            self._items.clear()


# Module-level registry. The harness reads from here; the CLI's
# ``--tests-config`` resolves plugin names against it.
registry = _Registry()


def register_plugin(plugin: Any) -> Tuple[str, str]:
    """Validate and add ``plugin`` to the module-level registry."""
    return registry.register(plugin)


def list_plugins() -> List[str]:
    """Return the construct ids of every registered plugin.

    Convenience wrapper around :data:`registry.keys()`. Returns the
    construct_id strings (the first element of each (construct_id,
    version) key), sorted alphabetically, with duplicates removed when
    multiple versions of the same construct are registered.
    """
    seen: List[str] = []
    for construct_id, _version in registry.keys():
        if construct_id not in seen:
            seen.append(construct_id)
    return sorted(seen)


__all__ = [
    "SubTestProtocol",
    "validate_plugin",
    "register_plugin",
    "list_plugins",
    "is_auxiliary_plugin",
    "requires_multi_turn_dispatch",
    "registry",
]
