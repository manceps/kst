"""Unit tests for the CaiciAdapter bearer-token authentication path.

Covers:

- Constructor accepts ``auth_bearer_token`` kwarg.
- When ``auth_bearer_token`` is set, the outgoing request carries the
  static bearer in the ``Authorization`` header.
- When the env var ``CAICI_API_KEY`` is set and no explicit kwarg is
  passed, the env value is honored.
- The legacy ``KST_CAICI_BEARER_TOKEN`` env var is honored as a
  fallback for tooling that already exports it.
- 401 on a static-bearer request surfaces as an :class:`AdapterError`
  (no silent retry).
- Requests without any bearer token go out unauthenticated (suitable
  for a local inference server that does not enforce auth).

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

import os
import unittest
from typing import Any, Dict, Optional
from unittest.mock import patch

from kst.adapters.caici_adapter import CaiciAdapter
from kst.envelope import AdapterRequest
from kst.errors import AdapterError


class _StubResp:
    def __init__(
        self,
        status_code: int = 200,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"cognitive_telemetry": {}},
        }
        self.text = "stub-body"
        self.headers: Dict[str, str] = {}

    def json(self) -> Dict[str, Any]:
        return self._payload


class TestAdapterBearerTokenConstructor(unittest.TestCase):
    def test_explicit_bearer_recorded(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token="OPERATOR-XYZ",
        )
        self.assertEqual(a.auth_bearer_token, "OPERATOR-XYZ")

    def test_caici_api_key_env_var_fallback(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("CAICI_API_KEY", "KST_CAICI_BEARER_TOKEN")}
        with patch.dict(
            os.environ,
            {**env_clean, "CAICI_API_KEY": "from-env"},
            clear=True,
        ):
            a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        self.assertEqual(a.auth_bearer_token, "from-env")

    def test_legacy_env_var_fallback(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("CAICI_API_KEY", "KST_CAICI_BEARER_TOKEN")}
        with patch.dict(
            os.environ,
            {**env_clean, "KST_CAICI_BEARER_TOKEN": "legacy-env"},
            clear=True,
        ):
            a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        self.assertEqual(a.auth_bearer_token, "legacy-env")

    def test_no_bearer_when_no_kwarg_and_no_env(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("CAICI_API_KEY", "KST_CAICI_BEARER_TOKEN")}
        with patch.dict(os.environ, env_clean, clear=True):
            a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        self.assertIsNone(a.auth_bearer_token)


class TestAdapterRequestPath(unittest.TestCase):
    def _make_request(self) -> AdapterRequest:
        return AdapterRequest(
            request_id="r-1",
            prompt="hi",
            system=None,
            max_tokens=8,
            temperature=0.0,
            stop_sequences=(),
        )

    def test_static_bearer_used_in_authorization_header(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token="OPERATOR",
        )

        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["headers"] = headers or {}
            return _StubResp(200)

        with patch(
            "kst.adapters.caici_adapter.requests.post",
            side_effect=fake_post,
        ):
            a._send_once(self._make_request())

        self.assertEqual(
            captured["headers"].get("Authorization"), "Bearer OPERATOR"
        )

    def test_unauthenticated_request_omits_authorization_header(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("CAICI_API_KEY", "KST_CAICI_BEARER_TOKEN")}
        with patch.dict(os.environ, env_clean, clear=True):
            a = CaiciAdapter(endpoint="http://x/v1/chat/completions")

        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["headers"] = headers or {}
            return _StubResp(200)

        with patch(
            "kst.adapters.caici_adapter.requests.post",
            side_effect=fake_post,
        ):
            a._send_once(self._make_request())

        self.assertNotIn("Authorization", captured["headers"])

    def test_static_bearer_401_surfaces_adapter_error(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token="OPERATOR",
        )

        call_count = {"n": 0}

        def fake_post(url, json=None, headers=None, timeout=None):
            call_count["n"] += 1
            return _StubResp(401)

        with patch(
            "kst.adapters.caici_adapter.requests.post",
            side_effect=fake_post,
        ):
            with self.assertRaises(AdapterError):
                a._send_once(self._make_request())
        self.assertEqual(
            call_count["n"], 1,
            "static-bearer 401 must NOT trigger a retry inside _send_once",
        )


class TestCliBuildAdapterPassesBearer(unittest.TestCase):
    def test_build_adapter_forwards_bearer(self) -> None:
        from kst import cli as kst_cli

        env_clean = {k: v for k, v in os.environ.items()
                     if k != "CAICI_ENDPOINT"}
        with patch.dict(
            os.environ,
            {**env_clean,
             "CAICI_ENDPOINT": "https://chat.cai.ci/v1/chat/completions"},
            clear=True,
        ):
            with patch(
                "kst.cli.CaiciAdapter", autospec=True
            ) as mock_cls:
                kst_cli.build_adapter("caici", auth_bearer_token="TKN-2")
        mock_cls.assert_called_with(auth_bearer_token="TKN-2")

    def test_build_adapter_caici_local_forwards_bearer(self) -> None:
        from kst import cli as kst_cli

        with patch(
            "kst.cli.CaiciAdapter", autospec=True
        ) as mock_cls:
            kst_cli.build_adapter("caici_local", auth_bearer_token="LOCAL-T")
        kwargs = mock_cls.call_args.kwargs
        self.assertEqual(kwargs.get("auth_bearer_token"), "LOCAL-T")
        self.assertEqual(
            kwargs.get("endpoint"), "http://localhost:8082/v1/chat/completions"
        )


class TestCliParserHasFlag(unittest.TestCase):
    def test_parser_accepts_auth_bearer_token_flag(self) -> None:
        from kst import cli as kst_cli

        parser = kst_cli.build_parser()
        args = parser.parse_args([
            "run",
            "--target", "caici_local",
            "--tests-config", "/tmp/x.yaml",
            "--auth-bearer-token", "MY-TOKEN",
            "--no-db",
        ])
        self.assertEqual(args.auth_bearer_token, "MY-TOKEN")


if __name__ == "__main__":
    unittest.main()
