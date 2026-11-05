"""Run the Doc2Agent trajectory evaluation against an external chat provider.

The adapter sends the same JSON-action conversation as the local Qwen3 runner.
It deliberately does not use provider-native tools or tool_choice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_doc2agent_qwen3 import (  # noqa: E402
    DEFAULT_TASKS,
    DEFAULT_TOOLS,
    ROOT,
    USER_PROMPT_TEMPLATE,
    ChatReply,
    compact_tool_catalog,
    load_tasks,
    load_tools,
    run_task_with_chat,
    system_prompt,
)

PROVIDER = "local_magpie"
DEFAULT_MODEL = "workbuddy-ai/glm-5.3"
DEFAULT_ENDPOINT = "http://127.0.0.1:3425/v1/chat/completions"
DEFAULT_API_KEY_ENV = "MAGPIE_API_KEY"
DEFAULT_OUT = ROOT / "reports" / "w3_day2" / "f3_glm53_50"
METRICS_SCOPE = "trajectory_only"
ANSWER_CORRECTNESS = "not_evaluated"
GRADER = "not_run_upstream_requires_gpt4o_api_key"


@dataclass(frozen=True)
class OpenAIConfig:
    model: str = DEFAULT_MODEL
    endpoint: str = DEFAULT_ENDPOINT
    api_key_env: str = DEFAULT_API_KEY_ENV
    temperature: float = 0.0
    max_tokens: int = 512
    request_timeout: float = 180.0

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must be an HTTP or HTTPS URL")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.temperature < 0:
            raise ValueError("temperature must not be negative")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")


class ExternalChatError(RuntimeError):
    """A safe, user-facing error without request credentials."""


def chat_payload(messages: list[dict[str, str]], config: OpenAIConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }


def parse_chat_response(data: Any, elapsed_seconds: float) -> ChatReply:
    if not isinstance(data, dict):
        raise ExternalChatError("malformed_response: body is not a JSON object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExternalChatError("malformed_response: choices must be a non-empty list")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ExternalChatError("malformed_response: choices[0] is not an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ExternalChatError("malformed_response: choices[0].message is not an object")
    content = message.get("content")
    if not isinstance(content, str):
        raise ExternalChatError(
            "malformed_response: choices[0].message.content is not a string"
        )
    usage = data.get("usage")
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        raise ExternalChatError("malformed_response: usage is not an object")
    finish_reason = choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        finish_reason = str(finish_reason)
    return ChatReply(
        content=content,
        elapsed_seconds=elapsed_seconds,
        finish_reason=finish_reason,
        usage=dict(usage),
    )


def _redact(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "<redacted>")


def call_openai_compatible(
    messages: list[dict[str, str]], config: OpenAIConfig
) -> ChatReply:
    api_key = os.environ.get(config.api_key_env, "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    started = time.perf_counter()
    try:
        response = requests.post(
            config.endpoint,
            json=chat_payload(messages, config),
            headers=headers,
            timeout=config.request_timeout,
        )
    except requests.RequestException as exc:
        detail = _redact(str(exc), api_key)
        raise ExternalChatError(
            f"network_error: {type(exc).__name__}: {detail}"
        ) from exc
    elapsed = time.perf_counter() - started

    if not response.ok:
        body = _redact(response.text[:500], api_key)
        raise ExternalChatError(
            f"http_error: status={response.status_code} body={body}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        detail = _redact(str(exc), api_key)
        raise ExternalChatError(f"malformed_response: invalid JSON: {detail}") from exc
    return parse_chat_response(data, elapsed)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def task_hash(tasks: list[dict[str, Any]]) -> str:
    return sha256_text(canonical_json(tasks))


def prompt_hashes(system: str, catalog: str) -> dict[str, str]:
    return {
        "system": sha256_text(system),
        "user_template": sha256_text(USER_PROMPT_TEMPLATE),
        "tool_catalog": sha256_text(catalog),
    }


def aggregate_usage(model_calls: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "responses_with_usage": 0,
    }
    for call in model_calls:
        usage = call.get("usage")
        if not isinstance(usage, dict) or not usage:
            continue
        totals["responses_with_usage"] += 1
        for key, value in usage.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            totals[key] = totals.get(key, 0) + value
    return totals


def finish_reason_counts(model_calls: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in model_calls:
        reason = call.get("finish_reason") or "not_provided"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def run_payload(run: Any) -> dict[str, Any]:
    return {
        "task_id": run.task_id,
        "question": run.question,
        "expected_tools": run.expected_tools,
        "tool_calls": run.tool_calls,
        "final_answer": run.final_answer,
        "errors": run.errors,
        "elapsed_seconds": round(run.elapsed_seconds, 3),
        **run.score(),
        "model_calls": len(run.model_calls),
        "model_responses": run.model_calls,
        "token_usage": aggregate_usage(run.model_calls),
        "finish_reasons": finish_reason_counts(run.model_calls),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--task-ids", default="")
    parser.add_argument("--max-rounds", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=180)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--tools", type=Path, default=DEFAULT_TOOLS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    tools = load_tools(args.tools)
    tasks = load_tasks(args.tasks)
    requested = {int(value) for value in args.task_ids.split(",") if value.strip()}
    if requested:
        tasks = [task for task in tasks if task["task_id"] in requested]
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        raise SystemExit("No tasks selected")

    config = OpenAIConfig(
        model=args.model,
        endpoint=args.endpoint,
        api_key_env=args.api_key_env,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        request_timeout=args.request_timeout,
    )
    catalog = compact_tool_catalog(tools)
    system = system_prompt(catalog)
    selected_task_hash = task_hash(tasks)
    args.out.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    all_model_calls: list[dict[str, Any]] = []
    started = time.perf_counter()
    for task in tasks:
        print(f"task {task['task_id']:02d}/{len(tasks):02d}", flush=True)
        run = run_task_with_chat(
            task,
            tools,
            args.max_rounds,
            system,
            lambda messages: call_openai_compatible(messages, config),
            chat_label="external",
        )
        payload = run_payload(run)
        runs.append(payload)
        all_model_calls.extend(run.model_calls)
        (args.out / f"task_{run.task_id:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = {
        "schema_version": 1,
        "provider": PROVIDER,
        "model": config.model,
        "endpoint": config.endpoint,
        "metrics_scope": METRICS_SCOPE,
        "answer_correctness": ANSWER_CORRECTNESS,
        "grader": GRADER,
        "tasks_run": len(runs),
        "max_rounds": args.max_rounds,
        "tools_available": len(tools),
        "prompt_hashes": prompt_hashes(system, catalog),
        "task_hash": selected_task_hash,
        "request_options": {
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": False,
            "request_timeout_seconds": config.request_timeout,
            "provider_native_tools": False,
            "tool_choice": "not_sent",
        },
        "exact_sequence": sum(run["exact_sequence"] for run in runs),
        "all_expected_called": sum(run["all_expected_called"] for run in runs),
        "any_expected_called": sum(run["any_expected_called"] for run in runs),
        "tasks_with_tool_call": sum(bool(run["tool_calls"]) for run in runs),
        "tasks_with_final_answer": sum(bool(run["final_answer"]) for run in runs),
        "tool_call_successes": sum(run["call_successes"] for run in runs),
        "tool_calls": sum(len(run["tool_calls"]) for run in runs),
        "model_calls": sum(run["model_calls"] for run in runs),
        "finish_reasons": finish_reason_counts(all_model_calls),
        "token_usage": aggregate_usage(all_model_calls),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
