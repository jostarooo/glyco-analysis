from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_esm150_lora_repro_gpu_test",
        ROOT / "scripts" / "run_esm150_lora_repro.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(
    os.environ.get("RUN_ESM150_GPU_TESTS") == "1",
    "set RUN_ESM150_GPU_TESTS=1 with the pinned compatibility overlay",
)
class AttentionForwardTests(unittest.TestCase):
    def test_rotary_sdpa_matches_eager_with_padding_mask(self):
        compat = Path(
            os.environ.get(
                "LORA_N_GLY_COMPAT_PATH",
                r"D:\uv\pylibs\lora-n-gly-peft014",
            )
        ).resolve()
        if not compat.is_dir():
            self.fail(f"Compatibility overlay not found: {compat}")
        sys.path.insert(0, str(compat))

        import torch
        import transformers
        from transformers import EsmConfig, EsmModel

        self.assertEqual(transformers.__version__, "4.50.3")

        runner = load_runner()
        torch.manual_seed(7)
        config = EsmConfig(
            vocab_size=33,
            hidden_size=64,
            num_hidden_layers=2,
            num_attention_heads=4,
            intermediate_size=128,
            max_position_embeddings=32,
            position_embedding_type="rotary",
            pad_token_id=1,
            hidden_dropout_prob=0.0,
            attention_probs_dropout_prob=0.0,
            token_dropout=False,
        )
        model = EsmModel(config).to("cuda").eval()
        input_ids = torch.randint(4, 32, (1, 17), device="cuda")
        attention_mask = torch.ones((1, 17), dtype=torch.long, device="cuda")
        attention_mask[:, -3:] = 0

        with torch.inference_mode():
            eager = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            ).last_hidden_state
            enabled, eligible = runner.install_sdpa_attention(
                model,
                config.num_hidden_layers,
            )
            sdpa = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            ).last_hidden_state

        self.assertEqual((enabled, eligible), (2, 2))
        self.assertEqual(eager.shape, sdpa.shape)
        self.assertLess(
            torch.max(torch.abs(eager - sdpa)).item(),
            1e-5,
        )


if __name__ == "__main__":
    unittest.main()
