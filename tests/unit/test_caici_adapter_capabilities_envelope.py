"""Unit tests for the CaiciAdapter ``caici_capabilities`` envelope.

The CAI.CI chat-completions endpoint accepts an open-dictionary
``caici_capabilities`` field on the request body (per its public
OpenAPI schema). KST surfaces operator control over this field via
the ``KST_CAICI_CAPABILITIES`` environment variable so harness
operators can flip server-side capabilities (e.g. research bypass)
without code changes.

These tests pin the env-var contract:

- Unset / empty: adapter omits the field (default chat-path).
- Valid JSON object with recognised keys: forwarded verbatim.
- Malformed JSON / non-dict shape / unknown keys / wrong-type values:
  logged as a warning and ignored entirely (no partial envelope).
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional
from unittest.mock import patch

from kst.adapters.caici_adapter import (
    CaiciAdapter,
    _parse_caici_capabilities_env,
)
from kst.envelope import AdapterRequest


class _StubResp:
    def __init__(
        self,
        status_code: int = 200,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"cognitive_telemetry": {}},
        }
        self.text = "stub-body"
        self.headers: Dict[str, str] = {}

    def json(self) -> Dict[str, Any]:
        return self._payload


def _make_request(request_id: str = "abc-123") -> AdapterRequest:
    return AdapterRequest(
        request_id=request_id,
        prompt="hi",
        system=None,
        max_tokens=8,
        temperature=0.0,
        stop_sequences=(),
    )


def _build_adapter() -> CaiciAdapter:
    return CaiciAdapter(
        endpoint="http://x/v1/chat/completions",
    )


class TestParseCapabilitiesEnv(unittest.TestCase):
    """Direct coverage of the env-string parser."""

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_parse_caici_capabilities_env(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_parse_caici_capabilities_env(""))

    def test_valid_envelope_parsed(self) -> None:
        out = _parse_caici_capabilities_env(
            '{"research_required": false, '
            '"step_c_credibility": false, '
            '"research_budget_s": 0.0}'
        )
        self.assertEqual(
            out,
            {
                "research_required": False,
                "step_c_credibility": False,
                "research_budget_s": 0.0,
            },
        )

    def test_partial_envelope_parsed(self) -> None:
        out = _parse_caici_capabilities_env('{"research_required": true}')
        self.assertEqual(out, {"research_required": True})

    def test_malformed_json_ignored(self) -> None:
        self.assertIsNone(_parse_caici_capabilities_env("{not json"))

    def test_non_dict_root_ignored(self) -> None:
        self.assertIsNone(_parse_caici_capabilities_env("[]"))
        self.assertIsNone(_parse_caici_capabilities_env('"oops"'))
        self.assertIsNone(_parse_caici_capabilities_env("42"))

    def test_unknown_key_ignored_entirely(self) -> None:
        # One unknown key drops the whole envelope so a typo does not
        # silently no-op against the server.
        out = _parse_caici_capabilities_env(
            '{"research_required": false, "totally_made_up": true}'
        )
        self.assertIsNone(out)

    def test_wrong_type_research_required_ignored(self) -> None:
        out = _parse_caici_capabilities_env('{"research_required": "false"}')
        self.assertIsNone(out)

    def test_wrong_type_step_c_credibility_ignored(self) -> None:
        out = _parse_caici_capabilities_env('{"step_c_credibility": 1}')
        self.assertIsNone(out)

    def test_negative_research_budget_ignored(self) -> None:
        out = _parse_caici_capabilities_env('{"research_budget_s": -1.0}')
        self.assertIsNone(out)

    def test_zero_research_budget_accepted(self) -> None:
        out = _parse_caici_capabilities_env('{"research_budget_s": 0}')
        self.assertEqual(out, {"research_budget_s": 0.0})

    def test_bool_for_research_budget_rejected(self) -> None:
        # ``True`` is technically ``isinstance(True, int)`` but a bool
        # for a numeric field is operator error; reject it.
        out = _parse_caici_capabilities_env('{"research_budget_s": true}')
        self.assertIsNone(out)


class TestEnvelopeOnOutboundRequest(unittest.TestCase):
    """End-to-end coverage of the envelope reaching the request body."""

    def test_envelope_absent_when_env_unset(self) -> None:
        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json or {}
            return _StubResp(200)

        with patch.dict("os.environ", {}, clear=False):
            # Defensive: env var may already be set in the test
            # environment; pop it for this test.
            import os as _os

            _os.environ.pop("KST_CAICI_CAPABILITIES", None)
            a = _build_adapter()
            with patch(
                "kst.adapters.caici_adapter.requests.post",
                side_effect=fake_post,
            ):
                a._send_once(_make_request())

        self.assertNotIn("caici_capabilities", captured["body"])

    def test_envelope_absent_when_env_empty(self) -> None:
        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json or {}
            return _StubResp(200)

        with patch.dict(
            "os.environ", {"KST_CAICI_CAPABILITIES": ""}, clear=False
        ):
            a = _build_adapter()
            with patch(
                "kst.adapters.caici_adapter.requests.post",
                side_effect=fake_post,
            ):
                a._send_once(_make_request())

        self.assertNotIn("caici_capabilities", captured["body"])

    def test_envelope_forwarded_when_env_set(self) -> None:
        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json or {}
            return _StubResp(200)

        env_json = (
            '{"research_required": false, '
            '"step_c_credibility": false, '
            '"research_budget_s": 0.0}'
        )
        with patch.dict(
            "os.environ",
            {"KST_CAICI_CAPABILITIES": env_json},
            clear=False,
        ):
            a = _build_adapter()
            with patch(
                "kst.adapters.caici_adapter.requests.post",
                side_effect=fake_post,
            ):
                a._send_once(_make_request())

        self.assertIn("caici_capabilities", captured["body"])
        self.assertEqual(
            captured["body"]["caici_capabilities"],
            {
                "research_required": False,
                "step_c_credibility": False,
                "research_budget_s": 0.0,
            },
        )

    def test_envelope_absent_on_malformed_env(self) -> None:
        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json or {}
            return _StubResp(200)

        with patch.dict(
            "os.environ",
            {"KST_CAICI_CAPABILITIES": "{not json"},
            clear=False,
        ):
            a = _build_adapter()
            with patch(
                "kst.adapters.caici_adapter.requests.post",
                side_effect=fake_post,
            ):
                a._send_once(_make_request())

        # Malformed JSON must not poison the request body; the field is
        # absent and default chat-path semantics are preserved.
        self.assertNotIn("caici_capabilities", captured["body"])

    def test_envelope_is_fresh_dict_per_call(self) -> None:
        """The body must contain a fresh dict so a caller that mutates
        body['caici_capabilities'] post-hoc does not leak into the
        next call.
        """
        captured: list = []

        def fake_post(url, json=None, headers=None, timeout=None):
            captured.append(json or {})
            return _StubResp(200)

        env_json = '{"research_required": false}'
        with patch.dict(
            "os.environ",
            {"KST_CAICI_CAPABILITIES": env_json},
            clear=False,
        ):
            a = _build_adapter()
            with patch(
                "kst.adapters.caici_adapter.requests.post",
                side_effect=fake_post,
            ):
                a._send_once(_make_request("r1"))
                # Mutate the first body's envelope; the second call
                # must not see the mutation.
                captured[0]["caici_capabilities"]["research_required"] = True
                a._send_once(_make_request("r2"))

        self.assertEqual(
            captured[1]["caici_capabilities"],
            {"research_required": False},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
