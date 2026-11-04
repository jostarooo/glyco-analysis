from __future__ import annotations

import importlib.util
import math
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .models import (
    PredictionResult,
    SitePrediction,
    find_sequons,
    normalize_sequence,
    sequence_sha256,
)


BASE_MODEL_ID = "facebook/esm2_t30_150M_UR50D"
BASE_MODEL_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
EXPECTED_ADAPTER_SHA256 = (
    "A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4"
)
EXPECTED_ADAPTER_TENSORS = 376
DEFAULT_ADAPTER_DIR = Path(
    r"D:\wbworkspace\LoRA-N-Gly\checkpoints\N-linked\ESM-150M\checkpoint"
)
DEFAULT_COMPAT_PATH = Path(r"D:\uv\pylibs\lora-n-gly-peft014")
LIMITATIONS = (
    "这是研究原型，不是临床诊断工具。",
    "概率来自分类头 softmax，未做外部概率校准。",
    "模型预测不等于体内实验证据；需要回到 UniProt 或原始论文核对。",
    "本轮只判断 N-X-S/T sequon，不覆盖 O-糖基化。",
)


class PredictorError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Esm150Predictor:
    def __init__(
        self,
        *,
        adapter_dir: Path = DEFAULT_ADAPTER_DIR,
        compat_path: Path = DEFAULT_COMPAT_PATH,
        base_model_id: str = BASE_MODEL_ID,
        base_model_revision: str = BASE_MODEL_REVISION,
        device: str = "cuda",
        attention_backend: str = "sdpa",
        offline: bool = True,
    ) -> None:
        self.adapter_dir = adapter_dir.resolve()
        self.compat_path = compat_path.resolve()
        self.base_model_id = base_model_id
        self.base_model_revision = base_model_revision
        self.device = device
        self.attention_backend = attention_backend
        self.offline = offline
        self._state = "cold"
        self._state_message = ""
        self._lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._module: Any | None = None
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._environment: dict[str, Any] = {}
        self._load_warnings: tuple[str, ...] = ()
        self._adapter_sha256 = ""
        self._adapter_tensor_count = 0
        self._read_adapter_metadata()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def state_message(self) -> str:
        with self._lock:
            return self._state_message

    def _read_adapter_metadata(self) -> None:
        adapter_file = self.adapter_dir / "adapter_model.safetensors"
        adapter_config = self.adapter_dir / "adapter_config.json"
        if not adapter_file.is_file() or not adapter_config.is_file():
            self._set_state("error", f"检查点目录不完整：{self.adapter_dir}")
            return

        import hashlib

        digest = hashlib.sha256(adapter_file.read_bytes()).hexdigest().upper()
        self._adapter_sha256 = digest
        if digest != EXPECTED_ADAPTER_SHA256:
            self._set_state("error", "适配器 SHA256 与固定基线不一致")
            return

        try:
            from safetensors import safe_open

            with safe_open(str(adapter_file), framework="pt") as handle:
                self._adapter_tensor_count = len(list(handle.keys()))
        except Exception as error:
            self._set_state("error", f"读取适配器张量失败：{type(error).__name__}")
            return

        if self._adapter_tensor_count != EXPECTED_ADAPTER_TENSORS:
            self._set_state("error", "适配器张量数量与固定基线不一致")

    def _set_state(self, state: str, message: str = "") -> None:
        with self._lock:
            self._state = state
            self._state_message = message

    def _load_repro_module(self) -> Any:
        if self._module is not None:
            return self._module
        helper_path = (
            Path(__file__).resolve().parents[1] / "scripts" / "run_esm150_lora_repro.py"
        )
        if not helper_path.is_file():
            raise PredictorError("MODEL_HELPER_MISSING", "找不到既有 ESM-150M 推理模块")
        module_name = "_glyco_live_esm150_runtime"
        spec = importlib.util.spec_from_file_location(module_name, helper_path)
        if spec is None or spec.loader is None:
            raise PredictorError("MODEL_HELPER_INVALID", "无法加载既有推理模块")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._module = module
        return module

    def preload(self) -> dict[str, Any]:
        self._ensure_loaded()
        return self.model_info()

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._state == "ready" and self._model is not None:
                return
            if self._state == "loading":
                raise PredictorError("MODEL_LOADING", "模型正在加载")
            if self._state == "error":
                raise PredictorError("MODEL_UNAVAILABLE", self._state_message or "模型不可用")
            self._state = "loading"
            self._state_message = ""

        try:
            module = self._load_repro_module()
            config = module.RunConfig(
                test_csv=Path("__system_runtime_unused__.csv"),
                adapter_dir=self.adapter_dir,
                base_model_id=self.base_model_id,
                base_model_revision=self.base_model_revision,
                out_dir=Path("__system_runtime_unused__"),
                compat_path=self.compat_path,
                device=self.device,
                batch_size=1,
                attention_backend=self.attention_backend,
                offline=self.offline,
            )
            model, tokenizer, environment, warnings = module.load_model(config)
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            self._set_state("error", message)
            raise PredictorError("MODEL_LOAD_FAILED", message) from error

        unexpected = [
            warning
            for warning in warnings
            if "classifier.original_module.out_proj.lora_A.default.weight" not in warning
            and "classifier.original_module.out_proj.lora_B.default.weight" not in warning
        ]
        if unexpected:
            self._set_state("error", "模型加载出现非预期告警")
            raise PredictorError(
                "MODEL_LOAD_WARNING",
                "模型加载出现非预期告警：" + " | ".join(unexpected[:3]),
            )

        self._model = model
        self._tokenizer = tokenizer
        self._environment = environment
        self._load_warnings = tuple(warnings)
        self._set_state("ready")

    def model_info(self) -> dict[str, Any]:
        device_name = self.device
        versions = self._environment.get("versions", {})
        if self._environment:
            device_name = self._environment.get("device", {}).get("name", self.device)
        return {
            "base_model_id": self.base_model_id,
            "base_model_revision": self.base_model_revision,
            "adapter_sha256": self._adapter_sha256,
            "adapter_tensor_count": self._adapter_tensor_count,
            "device": device_name,
            "state": self.state,
            "state_message": self.state_message,
            "attention_backend": self.attention_backend,
            "dtype": "float32",
            "full_sequence": True,
            "truncation": False,
            "windowing": False,
            "load_warnings": list(self._load_warnings),
            "versions": versions,
        }

    def predict(self, raw_sequence: str) -> PredictionResult:
        sequence = normalize_sequence(raw_sequence)
        sequons = find_sequons(sequence)
        if not sequons:
            return PredictionResult(
                sequence_sha256=sequence_sha256(sequence),
                sequence_length=len(sequence),
                candidates=(),
                elapsed_seconds=0.0,
                model=self.model_info(),
                limitations=LIMITATIONS,
            )

        self._ensure_loaded()
        assert self._model is not None
        assert self._tokenizer is not None
        module = self._load_repro_module()

        import torch

        with self._inference_lock:
            started = time.perf_counter()
            try:
                if self.device.startswith("cuda"):
                    torch.cuda.synchronize()
                encoded = self._tokenizer(sequence, return_tensors="pt")
                input_ids = encoded["input_ids"].to(self.device)
                attention_mask = encoded["attention_mask"].to(self.device)
                token_length = int(input_ids.shape[1])
                if token_length != len(sequence) + 2:
                    raise PredictorError(
                        "TOKEN_LENGTH_MISMATCH",
                        f"token 长度为 {token_length}，预期为 {len(sequence) + 2}",
                    )

                position_model = self._model.base_model.model
                with torch.inference_mode():
                    hidden = position_model.esm(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        return_dict=True,
                    ).last_hidden_state
                    candidates: list[SitePrediction] = []
                    for sequon in sequons:
                        logits = position_model.classifier(
                            hidden,
                            torch.tensor(
                                [sequon.position],
                                dtype=torch.long,
                                device=self.device,
                            ),
                        )[0]
                        logit_negative = float(logits[0].item())
                        logit_positive = float(logits[1].item())
                        if not math.isfinite(logit_negative) or not math.isfinite(
                            logit_positive
                        ):
                            raise PredictorError(
                                "NON_FINITE_LOGIT",
                                f"位点 {sequon.position} 出现非有限 logit",
                            )
                        _, prob_positive = module.softmax_two(
                            logit_negative,
                            logit_positive,
                        )
                        candidates.append(
                            SitePrediction(
                                position=sequon.position,
                                motif=sequon.motif,
                                prob_positive=prob_positive,
                                predicted_label=module.binary_argmax(
                                    logit_negative,
                                    logit_positive,
                                ),
                                logit_negative=logit_negative,
                                logit_positive=logit_positive,
                            )
                        )
                if self.device.startswith("cuda"):
                    torch.cuda.synchronize()
            except PredictorError:
                raise
            except RuntimeError as error:
                if "out of memory" in str(error).lower():
                    if self.device.startswith("cuda"):
                        torch.cuda.empty_cache()
                    raise PredictorError(
                        "CUDA_OUT_OF_MEMORY",
                        "显存不足，请缩短序列后重试",
                    ) from error
                raise PredictorError(
                    "MODEL_INFERENCE_FAILED",
                    f"模型推理失败：{type(error).__name__}",
                ) from error
            except Exception as error:
                raise PredictorError(
                    "MODEL_INFERENCE_FAILED",
                    f"模型推理失败：{type(error).__name__}",
                ) from error
            elapsed = time.perf_counter() - started

        return PredictionResult(
            sequence_sha256=sequence_sha256(sequence),
            sequence_length=len(sequence),
            candidates=tuple(candidates),
            elapsed_seconds=elapsed,
            model=self.model_info(),
            limitations=LIMITATIONS,
        )
