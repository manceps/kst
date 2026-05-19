"""Unit tests for the GoogleAdapter ``thinking_budget`` integration.

Covers the behaviour required to evaluate thinking-only Gemini models
(e.g. ``gemini-3.x-pro-preview``) which reject ``thinkingBudget=0`` and
otherwise silently consume the entire ``maxOutputTokens`` cap as hidden
reasoning, returning ``finishReason: MAX_TOKENS`` with empty visible
text:

- Constructor accepts ``thinking_budget`` kwarg.
- ``KST_GOOGLE_THINKING_BUDGET`` env var is honored when no kwarg is
  passed.
- A non-int env var value falls back to the default (1024) without
  raising.
- When ``thinking_budget > 0`` the outgoing request body carries
  ``generationConfig.thinkingConfig.thinkingBudget``; when 0, the
  field is omitted entirely (preserves the original v1.0.0 behaviour
  for non-thinking models).
- ``maxOutputTokens`` sent to Google equals the plugin's
  ``request.max_tokens`` plus the budget, so the plugin's intended
  visible-token envelope is preserved.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
import unittest
from typing import Any, Dict, Optional
from unittest.mock import patch

from kst.adapters.google_adapter import GoogleAdapter
from kst.envelope import AdapterRequest


class _StubResp:
    def __init__(
        self,
        status_code: int = 200,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {
            "candidates": [
                {
                    "content": {"parts": [{"text": "ok"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
        self.text = "stub-body"
        self.headers: Dict[str, str] = {}

    def json(self) -> Dict[str, Any]:
        return self._payload


def _make_request(max_tokens: int = 256) -> AdapterRequest:
    return AdapterRequest(
        request_id="t",
        prompt="hello",
        system=None,
        temperature=0.0,
        max_tokens=max_tokens,
        stop_sequences=(),
    )


class TestGoogleAdapterThinkingBudgetConstructor(unittest.TestCase):
    def test_explicit_budget_kwarg_recorded(self) -> None:
        a = GoogleAdapter(api_key="x", thinking_budget=512)
        self.assertEqual(a.thinking_budget, 512)

    def test_default_budget_is_1024(self) -> None:
        # Clear the env override so we read the documented default.
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "KST_GOOGLE_THINKING_BUDGET"}
        with patch.dict(os.environ, env_clean, clear=True):
            a = GoogleAdapter(api_key="x")
        self.assertEqual(a.thinking_budget, 1024)

    def test_env_var_override_honored(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "KST_GOOGLE_THINKING_BUDGET"}
        with patch.dict(
            os.environ,
            {**env_clean, "KST_GOOGLE_THINKING_BUDGET": "2048"},
            clear=True,
        ):
            a = GoogleAdapter(api_key="x")
        self.assertEqual(a.thinking_budget, 2048)

    def test_env_var_invalid_value_falls_back_to_default(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "KST_GOOGLE_THINKING_BUDGET"}
        with patch.dict(
            os.environ,
            {**env_clean, "KST_GOOGLE_THINKING_BUDGET": "not-a-number"},
            clear=True,
        ):
            a = GoogleAdapter(api_key="x")
        self.assertEqual(a.thinking_budget, 1024)

    def test_explicit_kwarg_takes_precedence_over_env(self) -> None:
        with patch.dict(
            os.environ,
            {"KST_GOOGLE_THINKING_BUDGET": "999"},
            clear=False,
        ):
            a = GoogleAdapter(api_key="x", thinking_budget=42)
        self.assertEqual(a.thinking_budget, 42)


class TestGoogleAdapterRequestBody(unittest.TestCase):
    def _capture_body(self, adapter: GoogleAdapter) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["body"] = json
            return _StubResp(200)

        with patch(
            "kst.adapters.google_adapter.requests.post",
            side_effect=fake_post,
        ):
            adapter._send_once(_make_request(max_tokens=256))
        return captured["body"]

    def test_thinking_config_present_when_budget_positive(self) -> None:
        a = GoogleAdapter(api_key="x", thinking_budget=1024)
        body = self._capture_body(a)
        gen_cfg = body["generationConfig"]
        self.assertIn("thinkingConfig", gen_cfg)
        self.assertEqual(gen_cfg["thinkingConfig"], {"thinkingBudget": 1024})

    def test_thinking_config_present_with_zero_when_budget_explicit_zero(self) -> None:
        # An explicit budget=0 must surface `thinkingConfig.thinkingBudget=0`
        # on the wire. Some Gemini variants (notably gemini-3.5-flash)
        # default to thinking-on when the field is omitted entirely; the
        # only documented way to opt out is to send the zero explicitly.
        a = GoogleAdapter(api_key="x", thinking_budget=0)
        body = self._capture_body(a)
        gen_cfg = body["generationConfig"]
        self.assertIn("thinkingConfig", gen_cfg)
        self.assertEqual(gen_cfg["thinkingConfig"], {"thinkingBudget": 0})

    def test_max_output_tokens_expanded_by_budget(self) -> None:
        # The plugin's intended visible budget (256) must be preserved
        # by expanding the wire-level cap with the thinking budget.
        a = GoogleAdapter(api_key="x", thinking_budget=512)
        body = self._capture_body(a)
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 256 + 512)

    def test_max_output_tokens_unchanged_when_budget_zero(self) -> None:
        a = GoogleAdapter(api_key="x", thinking_budget=0)
        body = self._capture_body(a)
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 256)

    def test_negative_budget_does_not_subtract_from_max_tokens(self) -> None:
        # Defensive: a negative budget (e.g. operator error or
        # accidental env var) must not reduce the plugin's visible
        # budget; max(0, budget) clamps the expansion.
        a = GoogleAdapter(api_key="x", thinking_budget=-100)
        body = self._capture_body(a)
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 256)
        self.assertNotIn("thinkingConfig", body["generationConfig"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
