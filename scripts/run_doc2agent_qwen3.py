"""Run the Doc2Agent 50-task tool-use smoke test with a local Qwen3 model.

This runner measures tool selection and execution. It does not reproduce the
upstream GPT-4o answer-quality grader.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
DOC2AGENT_ROOT = Path(r"D:\wbworkspace\Doc2Agent")
DEFAULT_TASKS = DOC2AGENT_ROOT / "test_glycan" / "glycan_tasks_classified.jsonl"
DEFAULT_TOOLS = DOC2AGENT_ROOT / "test_glycan" / "MCPTools"
DEFAULT_OUT = ROOT / "reports" / "w2_day1" / "f3_qwen3_8b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


@dataclass
class Tool:
    name: str
    signature: inspect.Signature
    description: str
    function: Any


@dataclass
class TaskRun:
    task_id: int
    question: str
    expected_tools: list[str]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def score(self) -> dict[str, Any]:
        called = [call["tool"] for call in self.tool_calls]
        expected = self.expected_tools
        return {
            "exact_sequence": called == expected,
            "all_expected_called": all(tool in called for tool in expected),
            "any_expected_called": any(tool in called for tool in expected),
            "expected_steps": len(expected),
            "called_steps": len(called),
            "call_successes": sum(call["status"] == "ok" for call in self.tool_calls),
        }


def load_tools(tool_dir: Path) -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    for path in sorted(tool_dir.glob("*.py")):
        module_name = f"doc2agent_tool_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if function.__module__ != module_name or name.startswith("_") or name.startswith("parse_"):
                continue
            doc = inspect.getdoc(function) or ""
            summary = next((line.strip() for line in doc.splitlines() if line.strip()), name)
            tools[name] = Tool(name, inspect.signature(function), summary, function)
    return tools


def normalize_expected(value: str) -> list[str]:
    names = [part.strip().strip("\"'") for part in value.split("->")]
    return [name for name in names if name]


def load_tasks(path: Path) -> list[dict[str, Any]]:
    tasks = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["task_id"] = index
        row["expected_tools"] = normalize_expected(row.get("expected_trajectory", ""))
        tasks.append(row)
    return tasks


def compact_tool_catalog(tools: dict[str, Tool]) -> str:
    lines = []
    for tool in sorted(tools.values(), key=lambda item: item.name):
        parameters = []
        for parameter in tool.signature.parameters.values():
            suffix = "" if parameter.default is inspect.Parameter.empty else "?"
            parameters.append(f"{parameter.name}{suffix}")
        description = re.sub(r"\s+", " ", tool.description).strip()
        lines.append(f"- {tool.name}({', '.join(parameters)}): {description}")
    return "\n".join(lines)


def system_prompt(catalog: str) -> str:
    return f"""You are a glycoinformatics tool-use agent. Select tools only from the catalog.
Use one tool at a time. After each tool result, decide whether another catalog
tool is needed or finish. Return exactly one JSON object in one of these forms:

{{"action":"call_tool","tool":"tool_name","arguments":{{"param":"value"}}}}
{{"action":"finish","answer":"concise evidence-based answer"}}

Do not invent tool names or parameter values. Preserve identifiers such as
accessions and WURCS strings exactly. Use the supplied tool result as evidence.

TOOL CATALOG
{catalog}
"""


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        value = json.loads(text[start : end + 1])
        return value if isinstance(value, dict) else {}


def coerce_arguments(tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(arguments)
    for name, parameter in tool.signature.parameters.items():
        if name not in coerced:
            continue
        value = coerced[name]
        annotation = parameter.annotation
        if annotation is int and isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            coerced[name] = int(value)
        elif annotation is float and isinstance(value, str):
            coerced[name] = float(value)
        elif annotation is bool and isinstance(value, str):
            coerced[name] = value.lower() in {"1", "true", "yes"}
    return coerced


def serialize_result(result: Any) -> Any:
    if isinstance(result, requests.Response):
        payload: Any
        try:
            payload = result.json()
        except ValueError:
            payload = result.text
        return {
            "status_code": result.status_code,
            "url": result.url,
            "data": payload,
        }
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return result
    return str(result)


def truncate_payload(value: Any, limit: int = 6000) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"truncated": True, "preview": text[:limit]}


def call_ollama(model: str, messages: list[dict[str, str]], seed: int) -> tuple[str, float]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "seed": seed,
            "num_ctx": 16384,
            "num_predict": 768,
        },
    }
    started = time.perf_counter()
    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    elapsed = time.perf_counter() - started
    return response.json()["message"]["content"], elapsed


def run_task(
    task: dict[str, Any],
    tools: dict[str, Tool],
    model: str,
    seed: int,
    max_rounds: int,
    system: str,
) -> TaskRun:
    run = TaskRun(task["task_id"], task["question"], task["expected_tools"])
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"/no_think\nQuestion: {task['question']}\n"
                "Choose the next tool or finish. Return JSON only."
            ),
        },
    ]
    for _ in range(max_rounds):
        try:
            content, _ = call_ollama(model, messages, seed)
        except Exception as exc:
            run.errors.append(f"ollama: {type(exc).__name__}: {exc}")
            break
        decision = parse_json_object(content)
        action = decision.get("action")
        if action == "finish":
            run.final_answer = str(decision.get("answer", ""))
            break
        if action != "call_tool":
            run.errors.append(f"invalid_action: {content[:500]}")
            break

        tool_name = str(decision.get("tool", ""))
        arguments = decision.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        tool = tools.get(tool_name)
        if tool is None:
            run.tool_calls.append(
                {"tool": tool_name, "arguments": arguments, "status": "unknown_tool"}
            )
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": f"Unknown tool {tool_name!r}. Choose a catalog tool or finish.",
                }
            )
            continue

        try:
            result = tool.function(**coerce_arguments(tool, arguments))
            status = "ok"
            error = ""
        except Exception as exc:
            result = None
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            run.errors.append(f"{tool_name}: {error}")
        record = {
            "tool": tool_name,
            "arguments": arguments,
            "status": status,
            "error": error,
            "result": truncate_payload(serialize_result(result)),
        }
        run.tool_calls.append(record)
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": "Tool result:\n"
                + json.dumps(record, ensure_ascii=False, default=str)
                + "\nChoose the next tool or finish with JSON.",
            }
        )
    else:
        run.errors.append("max_rounds_reached")

    run.elapsed_seconds = time.perf_counter() - started
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--task-ids", default="")
    parser.add_argument("--max-rounds", type=int, default=3)
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

    args.out.mkdir(parents=True, exist_ok=True)
    system = system_prompt(compact_tool_catalog(tools))
    runs = []
    started = time.perf_counter()
    for task in tasks:
        print(f"task {task['task_id']:02d}/{len(tasks):02d}", flush=True)
        run = run_task(task, tools, args.model, args.seed, args.max_rounds, system)
        payload = {
            "task_id": run.task_id,
            "question": run.question,
            "expected_tools": run.expected_tools,
            "tool_calls": run.tool_calls,
            "final_answer": run.final_answer,
            "errors": run.errors,
            "elapsed_seconds": round(run.elapsed_seconds, 3),
            **run.score(),
        }
        runs.append(payload)
        (args.out / f"task_{run.task_id:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = {
        "model": args.model,
        "seed": args.seed,
        "tasks_run": len(runs),
        "max_rounds": args.max_rounds,
        "tools_available": len(tools),
        "exact_sequence": sum(run["exact_sequence"] for run in runs),
        "all_expected_called": sum(run["all_expected_called"] for run in runs),
        "any_expected_called": sum(run["any_expected_called"] for run in runs),
        "tasks_with_tool_call": sum(bool(run["tool_calls"]) for run in runs),
        "tasks_with_final_answer": sum(bool(run["final_answer"]) for run in runs),
        "tool_call_successes": sum(run["call_successes"] for run in runs),
        "tool_calls": sum(len(run["tool_calls"]) for run in runs),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "grader": "not_run_upstream_requires_gpt4o_api_key",
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
