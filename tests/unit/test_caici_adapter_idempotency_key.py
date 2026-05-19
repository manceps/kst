"""Unit tests for the CaiciAdapter ``X-CAICI-Idempotency-Key`` header.

The CAI.CI proxy / wake supports an idempotency cache keyed off the
``X-CAICI-Idempotency-Key`` request header. When the adapter retries a
request after a transient failure, reusing the same key lets the
backend return the cached completion instead of re-executing the
chat path; that turns the cost of a retry-storm from compounding to
constant.

The key is derived from ``AdapterRequest.request_id`` so it is
unique per logical request and stable across retries of that one
request.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional
from unittest.mock import patch

from kst.adapters.caici_adapter import CaiciAdapter
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


class TestIdempotencyKeyHeader(unittest.TestCase):
    def test_idempotency_key_header_is_set_on_every_request(self) -> None:
        a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        captured: Dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["headers"] = headers or {}
            return _StubResp(200)

        with patch(
            "kst.adapters.caici_adapter.requests.post",
            side_effect=fake_post,
        ):
            a._send_once(_make_request("abc-123"))

        self.assertIn("X-CAICI-Idempotency-Key", captured["headers"])
        self.assertEqual(
            captured["headers"]["X-CAICI-Idempotency-Key"],
            "kst-abc-123",
        )

    def test_idempotency_key_is_stable_across_retries_of_same_request(self) -> None:
        """The header must be a function of the AdapterRequest, not a
        fresh value per call. Re-sending the same request twice (as
        the BaseAdapter retry loop does) must surface the same key
        so the backend cache hits.
        """
        a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        captured_keys: list = []

        def fake_post(url, json=None, headers=None, timeout=None):
            captured_keys.append((headers or {}).get("X-CAICI-Idempotency-Key"))
            return _StubResp(200)

        req = _make_request("request-XYZ")
        with patch(
            "kst.adapters.caici_adapter.requests.post",
            side_effect=fake_post,
        ):
            a._send_once(req)
            a._send_once(req)  # simulate retry: same request, second call.

        self.assertEqual(len(captured_keys), 2)
        self.assertEqual(captured_keys[0], captured_keys[1])
        self.assertEqual(captured_keys[0], "kst-request-XYZ")

    def test_idempotency_key_differs_across_distinct_requests(self) -> None:
        """Two different logical requests must surface different keys
        so the backend cache does not return the wrong completion.
        """
        a = CaiciAdapter(endpoint="http://x/v1/chat/completions")
        captured_keys: list = []

        def fake_post(url, json=None, headers=None, timeout=None):
            captured_keys.append((headers or {}).get("X-CAICI-Idempotency-Key"))
            return _StubResp(200)

        with patch(
            "kst.adapters.caici_adapter.requests.post",
            side_effect=fake_post,
        ):
            a._send_once(_make_request("alpha"))
            a._send_once(_make_request("beta"))

        self.assertEqual(captured_keys[0], "kst-alpha")
        self.assertEqual(captured_keys[1], "kst-beta")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
