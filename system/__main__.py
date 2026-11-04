from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import subprocess
from pathlib import Path

from .auth import (
    AuthService,
    DEMO_PASSWORD_HASH,
    DEMO_USERNAME,
    hash_password,
)
from .http_app import AppContext, make_server
from .http_app import load_index_html
from .jobs import JobService
from .predictor import (
    DEFAULT_ADAPTER_DIR,
    DEFAULT_COMPAT_PATH,
    Esm150Predictor,
)
from .samples import SampleProvider


REPO_ROOT = Path(__file__).resolve().parents[1]


def current_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def predictor_from_environment() -> Esm150Predictor:
    return Esm150Predictor(
        adapter_dir=Path(
            os.environ.get("GLYCO_ADAPTER_DIR", str(DEFAULT_ADAPTER_DIR))
        ),
        compat_path=Path(
            os.environ.get("GLYCO_COMPAT_PATH", str(DEFAULT_COMPAT_PATH))
        ),
        device=os.environ.get("GLYCO_DEVICE", "cuda"),
        offline=True,
    )


def auth_from_environment(*, host: str) -> AuthService:
    username = os.environ.get("GLYCO_USERNAME", DEMO_USERNAME)
    configured_hash = os.environ.get("GLYCO_PASSWORD_HASH", "")
    if not is_loopback(host) and not configured_hash:
        raise SystemExit(
            "拒绝启动：绑定非回环地址时必须设置 GLYCO_PASSWORD_HASH，"
            "不能使用本地演示账号。"
        )
    return AuthService(username, configured_hash or DEMO_PASSWORD_HASH)


def doctor(*, preload: bool) -> int:
    predictor = predictor_from_environment()
    sample = SampleProvider(REPO_ROOT).load()
    payload = {
        "head": current_head(REPO_ROOT),
        "index_present": (REPO_ROOT / "system" / "static" / "index.html").is_file(),
        "sample_accession": sample.accession if sample else None,
        "sample_sequence_length": len(sample.sequence) if sample else None,
        "model": predictor.model_info(),
    }
    if preload:
        try:
            predictor.preload()
        except Exception as error:
            payload["preload_error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        else:
            payload["model"] = predictor.model_info()
            payload["preload"] = "PASS"
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if predictor.state == "error" or "preload_error" in payload:
        return 1
    return 0


def serve(args: argparse.Namespace) -> int:
    if not is_loopback(args.host):
        raise SystemExit(
            "拒绝启动：研究原型默认只允许绑定回环地址。"
            "如需局域网演示，请使用 HTTPS 反向代理或 SSH 隧道。"
        )

    predictor = predictor_from_environment()
    if predictor.state == "error":
        raise SystemExit(f"模型检查点不可用：{predictor.state_message}")
    if args.preload:
        predictor.preload()

    context = AppContext(
        head=current_head(REPO_ROOT),
        auth=auth_from_environment(host=args.host),
        jobs=JobService(
            predictor,
            max_queue=args.max_queue,
            ttl_seconds=args.ttl_seconds,
        ),
        predictor=predictor,
        samples=SampleProvider(REPO_ROOT),
        index_html=load_index_html(REPO_ROOT),
    )
    server = make_server(context, host=args.host, port=args.port)
    print(
        f"glyco-analysis-system listening on http://{args.host}:{server.server_port} "
        f"head={context.head[:8]}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("stopping", flush=True)
    finally:
        server.server_close()
        context.jobs.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m system",
        description="W3 authenticated N-linked site prediction system",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="start the local system")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--max-queue", type=int, default=4)
    serve_parser.add_argument("--ttl-seconds", type=int, default=1800)
    serve_parser.add_argument("--preload", action="store_true")
    serve_parser.set_defaults(handler=serve)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="check the checkpoint metadata and optional real model load",
    )
    doctor_parser.add_argument("--preload", action="store_true")
    doctor_parser.set_defaults(handler=lambda args: doctor(preload=args.preload))

    password_parser = subparsers.add_parser(
        "hash-password",
        help="read a password from stdin and print its PBKDF2 hash",
    )
    password_parser.set_defaults(handler=hash_password_command)
    return parser


def hash_password_command(_: argparse.Namespace) -> int:
    password = getpass.getpass("password: ")
    if password != getpass.getpass("confirm: "):
        raise SystemExit("两次输入不一致。")
    print(hash_password(password))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
