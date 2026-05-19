"""HuggingFace local-model adapter.

Black-box adapter that loads any ``transformers``-compatible
checkpoint on the local machine and runs greedy or sampled
generation. The adapter lazily imports ``transformers`` so that
environments without it can still exercise the rest of the KST
module.

Retry semantics inherit from :class:`BaseAdapter` but typically do
not fire: local generation either succeeds or hits a hard CUDA / OOM
error that is not productively retried.

Author: Al Kari, Manceps Inc.
"""

from __future__ import annotations

from typing import Any, Optional

from kst.adapters.base import BaseAdapter
from kst.envelope import (
    AdapterCapabilities,
    AdapterCapability,
    AdapterRequest,
    AdapterResponse,
)
from kst.errors import AdapterError


class HFLocalAdapter(BaseAdapter):
    """Wraps a HuggingFace causal-LM checkpoint for KST runs."""

    name = "hf_local"
    capability = AdapterCapability.BLACK_BOX

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-0.6B",
        device: str = "auto",
        dtype: str = "auto",
        trust_remote_code: bool = True,
        max_attempts: int = 1,
        timeout_s: float = 600.0,
    ) -> None:
        super().__init__(
            max_attempts=max_attempts,
            timeout_s=timeout_s,
        )
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.trust_remote_code = trust_remote_code
        self._model: Optional[Any] = None
        self._tokenizer: Optional[Any] = None

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            capability=self.capability,
            rate_limit_rpm=None,
            supports_seed=True,
            supports_logprobs=False,
            supports_grey_box_telemetry=False,
            max_tokens=4096,
            default_model_id=self.model_id,
        )

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except ImportError as exc:
            raise AdapterError(
                f"transformers / torch not installed: {exc}",
                adapter=self.name,
            ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, trust_remote_code=self.trust_remote_code
        )
        if self.dtype == "bf16":
            torch_dtype = torch.bfloat16
        elif self.dtype == "fp16":
            torch_dtype = torch.float16
        elif self.dtype == "fp32":
            torch_dtype = torch.float32
        else:
            torch_dtype = "auto"
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            trust_remote_code=self.trust_remote_code,
            device_map=self.device if self.device != "auto" else "auto",
            torch_dtype=torch_dtype,
        )

    def _send_once(self, request: AdapterRequest) -> AdapterResponse:
        try:
            self._ensure_loaded()
        except AdapterError:
            raise
        assert self._tokenizer is not None
        assert self._model is not None

        if request.system:
            prompt = f"{request.system}\n\n{request.prompt}"
        else:
            prompt = request.prompt

        inputs = self._tokenizer(prompt, return_tensors="pt")
        try:
            inputs = inputs.to(self._model.device)
        except Exception:  # noqa: BLE001
            pass

        gen_kwargs = {
            "max_new_tokens": request.max_tokens,
            "do_sample": request.temperature > 0,
            "temperature": max(request.temperature, 1e-5),
        }
        if request.seed is not None:
            try:
                import torch  # type: ignore

                torch.manual_seed(int(request.seed))
            except ImportError:
                pass

        try:
            out = self._model.generate(**inputs, **gen_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(
                f"HF generate failed: {type(exc).__name__}: {exc}",
                adapter=self.name,
            ) from exc

        generated = out[0, inputs["input_ids"].shape[1]:]
        text = self._tokenizer.decode(generated, skip_special_tokens=True)

        return AdapterResponse(
            request_id=request.request_id,
            text=text,
            model_id=self.model_id,
            adapter_name=self.name,
            capability=self.capability,
            status_code=200,
        )

    def close(self) -> None:
        self._model = None
        self._tokenizer = None
