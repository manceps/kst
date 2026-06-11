"""KST adapter package.

Adapters bridge the harness to concrete target systems. The
:class:`AdapterProtocol` in :mod:`kst.adapters.base` defines
the contract; concrete adapters live in sibling modules.

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from kst.adapters.anthropic_adapter import AnthropicAdapter
from kst.adapters.base import AdapterProtocol, BaseAdapter
from kst.adapters.caici_adapter import CaiciAdapter, map_cognitive_telemetry
from kst.adapters.google_adapter import GoogleAdapter
from kst.adapters.hf_local_adapter import HFLocalAdapter
from kst.adapters.openai_adapter import OpenAIAdapter

__all__ = [
    "AdapterProtocol",
    "BaseAdapter",
    "AnthropicAdapter",
    "CaiciAdapter",
    "GoogleAdapter",
    "HFLocalAdapter",
    "OpenAIAdapter",
    "map_cognitive_telemetry",
]
