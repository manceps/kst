"""Unit tests for the CaiciAdapter T2 bearer-token override.

Covers:

- Constructor accepts ``auth_bearer_token`` kwarg.
- When ``auth_bearer_token`` is set, the Firebase token manager is NOT
  created and the outgoing request carries the static bearer.
- When the env var ``KST_CAICI_BEARER_TOKEN`` is set and no explicit
  kwarg is passed, the env value is honored.
- 401 on a static-bearer request does NOT trigger a Firebase refresh
  (we surface the AdapterError instead).
- Existing Firebase anonymous flow remains intact when no bearer is
  supplied.

Author: Al Kari, Manceps Inc., research@manceps.com.
"""

from __future__ import annotations

import os
import unittest
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from kst.adapters.caici_adapter import CaiciAdapter
from kst.envelope import AdapterRequest
from kst.errors import AdapterError


class _StubResp:
    def __init__(self, status_code: int = 200, payload: Optional[Dict[str, Any]] = None) -> None:
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
    def test_explicit_bearer_disables_firebase_token_mgr(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            firebase_api_key="some-key",
            auth_bearer_token="T2-XYZ",
        )
        self.assertEqual(a.auth_bearer_token, "T2-XYZ")
        self.assertIsNone(
            a._token_mgr,
            "Firebase token manager must be None when a static bearer is set",
        )

    def test_env_var_fallback(self) -> None:
        with patch.dict(os.environ, {"KST_CAICI_BEARER_TOKEN": "from-env"}, clear=False):
            a = CaiciAdapter(
                endpoint="http://x", firebase_api_key="k",
            )
        self.assertEqual(a.auth_bearer_token, "from-env")
        self.assertIsNone(a._token_mgr)

    def test_no_bearer_keeps_firebase_flow(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "KST_CAICI_BEARER_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            a = CaiciAdapter(
                endpoint="http://x", firebase_api_key="some-key",
            )
        self.assertIsNone(a.auth_bearer_token)
        self.assertIsNotNone(a._token_mgr)

    def test_explicit_bearer_token_file_recorded(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token_file="/tmp/kst_test_token.txt",
        )
        self.assertEqual(a.auth_bearer_token_file, "/tmp/kst_test_token.txt")

    def test_bearer_token_file_env_var_fallback(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("CAICI_API_KEY", "KST_CAICI_BEARER_TOKEN",
                                  "KST_CAICI_BEARER_TOKEN_FILE")}
        with patch.dict(
            os.environ,
            {**env_clean, "KST_CAICI_BEARER_TOKEN_FILE": "/tmp/kst_test_token.txt"},
            clear=True,
        ):
            a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        self.assertEqual(a.auth_bearer_token_file, "/tmp/kst_test_token.txt")


class TestAdapterBearerTokenFileResolution(unittest.TestCase):
    """Verify the file-based bearer token is re-read per request so a
    wrapper can rotate the token during a long-running run."""

    def setUp(self) -> None:
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.token_path = os.path.join(self._td.name, "token.txt")

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write(self, value: str) -> None:
        with open(self.token_path, "w") as f:
            f.write(value)

    def test_file_token_read_on_resolve(self) -> None:
        self._write("token-v1\n")
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token_file=self.token_path,
        )
        self.assertEqual(a._resolve_bearer_token(), "token-v1")

    def test_file_token_rotation_observed_without_restart(self) -> None:
        self._write("token-v1")
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token_file=self.token_path,
        )
        self.assertEqual(a._resolve_bearer_token(), "token-v1")
        # Rotate the file.
        self._write("token-v2")
        self.assertEqual(a._resolve_bearer_token(), "token-v2")

    def test_empty_file_falls_back_to_static_bearer(self) -> None:
        self._write("")
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token="static-fallback",
            auth_bearer_token_file=self.token_path,
        )
        self.assertEqual(a._resolve_bearer_token(), "static-fallback")

    def test_missing_file_falls_back_to_static_bearer(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            auth_bearer_token="static-fallback",
            auth_bearer_token_file="/nonexistent/token.txt",
        )
        self.assertEqual(a._resolve_bearer_token(), "static-fallback")

    def test_missing_file_and_no_static_returns_none(self) -> None:
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("CAICI_API_KEY", "KST_CAICI_BEARER_TOKEN",
                                  "KST_CAICI_BEARER_TOKEN_FILE")}
        with patch.dict(os.environ, env_clean, clear=True):
            a = CaiciAdapter(
                endpoint="http://x/v1/chat/completions",
                auth_bearer_token_file="/nonexistent/token.txt",
            )
        self.assertIsNone(a._resolve_bearer_token())


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
            firebase_api_key="key",
            auth_bearer_token="T2-OPERATOR",
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
            captured["headers"].get("Authorization"), "Bearer T2-OPERATOR"
        )

    def test_static_bearer_401_does_not_refresh(self) -> None:
        a = CaiciAdapter(
            endpoint="http://x/v1/chat/completions",
            firebase_api_key="key",
            auth_bearer_token="T2-OPERATOR",
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
            "static-bearer 401 must NOT trigger a retry",
        )


class TestCliBuildAdapterPassesBearer(unittest.TestCase):
    def test_build_adapter_forwards_bearer(self) -> None:
        from kst import cli as stt_cli

        with patch(
            "kst.cli.CaiciAdapter", autospec=True
        ) as mock_cls:
            stt_cli.build_adapter("caici", auth_bearer_token="TKN-2")
        mock_cls.assert_called_with(auth_bearer_token="TKN-2")

    def test_build_adapter_caici_local_forwards_bearer(self) -> None:
        from kst import cli as stt_cli

        with patch(
            "kst.cli.CaiciAdapter", autospec=True
        ) as mock_cls:
            stt_cli.build_adapter("caici_local", auth_bearer_token="LOCAL-T")
        kwargs = mock_cls.call_args.kwargs
        self.assertEqual(kwargs.get("auth_bearer_token"), "LOCAL-T")
        self.assertEqual(
            kwargs.get("endpoint"), "http://localhost:8082/v1/chat/completions"
        )


class TestCliParserHasFlag(unittest.TestCase):
    def test_parser_accepts_auth_bearer_token_flag(self) -> None:
        from kst import cli as stt_cli

        parser = stt_cli.build_parser()
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
