"""验证本机 PyTorch + GPU 环境，并写出 reports/env_check.md。

判据（可行性第一关）：
  1. torch 能 import，版本与 CUDA 版本可见；
  2. torch.cuda.is_available() 为真；
  3. 在 GPU 上跑一次真实矩阵乘，结果与 CPU 一致；
  4. 读出显存容量与算力代号（RTX 5060 应为 sm_120）。

用法：
    .venv\\Scripts\\python.exe scripts\\env_check.py
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import shutil
import sys

import torch


def user_env(name: str) -> str:
    """进程环境变量优先；否则读注册表里的用户级变量（新开的终端才继承，脚本里自己兜底）。"""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return "(未设)"


def disk_free_gb(path: str) -> float:
    try:
        return round(shutil.disk_usage(path).free / 1024**3, 1)
    except OSError:
        return -1.0


def main() -> int:
    lines: list[str] = []
    ok = True

    lines.append(f"# 环境自检 {dt.date.today().isoformat()}")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 主机 | {platform.node()} · {platform.system()} {platform.release()} |")
    lines.append(f"| Python | {sys.version.split()[0]} ({sys.executable}) |")
    lines.append(f"| PyTorch | {torch.__version__} |")
    lines.append(f"| 编译 CUDA | {torch.version.cuda} |")
    lines.append(f"| cuDNN | {torch.backends.cudnn.version()} |")
    lines.append(f"| 线程数 | {torch.get_num_threads()} |")
    lines.append(f"| C: 可用 | {disk_free_gb('C:\\\\')} GB |")
    lines.append(f"| D: 可用 | {disk_free_gb('D:\\\\')} GB |")
    lines.append(f"| HF_HOME | {user_env('HF_HOME')} |")
    lines.append(f"| HF_ENDPOINT | {user_env('HF_ENDPOINT')} |")
    lines.append(f"| UV_CACHE_DIR | {user_env('UV_CACHE_DIR')} |")

    lines.append("")
    if not torch.cuda.is_available():
        lines.append("## 结论：失败")
        lines.append("")
        lines.append("`torch.cuda.is_available()` 为 False。检查是否装了 CPU 版 wheel，或驱动是否支持 cu128。")
        ok = False
    else:
        idx = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(idx)
        free_b, total_b = torch.cuda.mem_get_info(idx)
        lines.append("## GPU")
        lines.append("")
        lines.append("| 项 | 值 |")
        lines.append("|---|---|")
        lines.append(f"| 设备 | {props.name} |")
        lines.append(f"| 算力代号 | sm_{props.major}{props.minor} |")
        lines.append(f"| 显存总量 | {total_b / 1024**3:.2f} GiB |")
        lines.append(f"| 显存可用 | {free_b / 1024**3:.2f} GiB |")
        lines.append(f"| bf16 支持 | {torch.cuda.is_bf16_supported()} |")

        torch.manual_seed(0)
        a_cpu = torch.randn(512, 512, dtype=torch.float32)
        b_cpu = torch.randn(512, 512, dtype=torch.float32)
        expect = a_cpu @ b_cpu
        a = a_cpu.cuda()
        b = b_cpu.cuda()
        torch.cuda.synchronize()
        got = a @ b
        torch.cuda.synchronize()
        max_err = (got.cpu() - expect).abs().max().item()
        lines.append(f"| 512×512 矩阵乘最大误差 | {max_err:.3e} |")
        if max_err > 1e-2:
            ok = False
        lines.append("")
        lines.append("## 结论：" + ("通过" if ok else "失败"))

    report = "\n".join(lines) + "\n"
    print(report)
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "env_check.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
