"""PyG RGCNConv smoke test for the F2 line (W2 Day 1 decision).

Verifies that a relation-aware RGCN layer runs forward and backward on the
local GPU (RTX 5060, sm_120) with the torch build used by the project.
Exit code 0 only when every assertion passes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import torch
from torch_geometric.nn import RGCNConv

NUM_NODES = 64
NUM_EDGES = 256
NUM_RELATIONS = 4
IN_CHANNELS = 32
HIDDEN = 16


def main() -> int:
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available")

    device = torch.device("cuda:0")
    torch.manual_seed(0)
    torch.cuda.empty_cache()
    # This Windows torch build rejects an explicit device for peak-memory stats.
    torch.cuda.reset_peak_memory_stats()

    x = torch.randn(NUM_NODES, IN_CHANNELS, device=device)
    edge_index = torch.randint(0, NUM_NODES, (2, NUM_EDGES), device=device)
    edge_type = torch.randint(0, NUM_RELATIONS, (NUM_EDGES,), device=device)

    conv = RGCNConv(IN_CHANNELS, HIDDEN, NUM_RELATIONS, num_bases=2).to(device)
    head = torch.nn.Linear(HIDDEN, 1).to(device)
    labels = torch.randint(0, 2, (NUM_NODES,), device=device).float()

    torch.cuda.synchronize(device)
    started = time.perf_counter()
    hidden = conv(x, edge_index, edge_type).relu()
    logits = head(hidden).squeeze(-1)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
    forward_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    loss.backward()
    torch.cuda.synchronize(device)
    backward_ms = (time.perf_counter() - started) * 1000

    checks = {
        "hidden_finite": bool(torch.isfinite(hidden).all()),
        "loss_finite": bool(torch.isfinite(loss)),
        "conv_grad_finite": bool(
            all(
                torch.isfinite(p.grad).all()
                for p in conv.parameters()
                if p.grad is not None
            )
        ),
        "conv_grad_present": all(p.grad is not None for p in conv.parameters()),
        "head_grad_present": all(p.grad is not None for p in head.parameters()),
    }
    checks = {k: v for k, v in checks.items()}

    # The first CUDA call loads the sm_120 kernels; measure steady state after
    # a warm-up so the reported latency is not dominated by module load.
    steady_ms = []
    for _ in range(5):
        conv.zero_grad(set_to_none=True)
        head.zero_grad(set_to_none=True)
        torch.cuda.synchronize(device)
        tick = time.perf_counter()
        step_hidden = conv(x, edge_index, edge_type).relu()
        step_loss = torch.nn.functional.binary_cross_entropy_with_logits(
            head(step_hidden).squeeze(-1), labels
        )
        step_loss.backward()
        torch.cuda.synchronize(device)
        steady_ms.append((time.perf_counter() - tick) * 1000)

    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "torch": torch.__version__,
        "pyg": __import__("torch_geometric").__version__,
        "cuda_available": True,
        "device": torch.cuda.get_device_name(device),
        "capability": ".".join(str(v) for v in torch.cuda.get_device_capability(device)),
        "nodes": NUM_NODES,
        "edges": NUM_EDGES,
        "relations": NUM_RELATIONS,
        "forward_ms": round(forward_ms, 3),
        "backward_ms": round(backward_ms, 3),
        "steady_fwd_bwd_ms": round(sum(steady_ms) / len(steady_ms), 3),
        "loss": round(float(loss.detach().cpu()), 6),
        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 2),
        "checks": checks,
    }

    out = Path(__file__).resolve().parents[1] / "reports" / "w2_day1" / "pyg_rgcn_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
