"""Probe the 70 Doc2Agent glycan tool wrappers and record endpoint survival.

Each upstream file defines one function that performs a read-only database
query. The script imports every wrapper, calls it with default arguments (or a
small sample value for required parameters), and classifies the HTTP result.
"""

from __future__ import annotations

import csv
import importlib.util
import inspect
import json
import re
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

TOOL_ROOT = Path(r"D:\wbworkspace\Doc2Agent\_extracted\glycan\glycan")
OUT_DIR = Path(__file__).resolve().parents[1] / "reports" / "w2_day1"
URL_RE = re.compile(r'api_url\s*=\s*(?:f)?"([^"]+)"')
REQUIRED_SAMPLES = {
    "iupacextended": "Gal(b1-4)GlcNAc(b1-4)Glc",
    "smiles": "CCO",
    "dbid": "rs1042522",
    "accession": "P01857",
    "body": {"sequence": "MKTAYIAKQRQISFVKSHFSRQ"},
    "upi": "UPI0000000001",
    "type": "domain",
    "terms": "P01857",
    "taxonomy": "9606",
    "locations": "NC_000001.11:1-1000",
    "wurcs": "WURCS=2.0/2,2,1/[a2122h-1b_1-5_2*NCC/3=O][a2112h-1b_1-5]/1-2/a4-b1",
    "composition": "HexNAc(1)Hex(1)",
    "pUUID": "test",
    "text": "Gal(b1-4)GlcNAc",
    "gws": "Gal(b1-4)GlcNAc",
    "gtcid": "G17689DH",
    "target_db": "compound",
    "dbentry": "D00001",
    "dbentries": "C00002",
    "query_protein": "P01857",
    "aid": "1",
    "cid": "2244",
    "compound_name": "aspirin",
    "upid": "UP000005640",
    "hgvs": "p.Val600Glu",
    "dbtype": "EMBL",
    "accession_locations": "P01857:1-100",
    "getcolumns": "pdb,uniprot",
}
HTTP_CAPTURE = threading.local()
REACHABLE_CLASSES = {
    "ok",
    "api_error",
    "bad_request",
    "auth_required",
    "rate_limited",
    "not_found",
    "server_error",
    "http_424",
}


def patch_requests() -> None:
    original = requests.Session.request

    def bounded(self, method, url, **kwargs):
        timeout = kwargs.get("timeout")
        if not isinstance(timeout, (int, float)):
            timeout = 30
        kwargs["timeout"] = min(float(timeout), 30.0)
        kwargs.setdefault("stream", True)
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("User-Agent", "glyco-analysis-w2-inventory/0.1")
        kwargs["headers"] = headers
        response = original(self, method, url, **kwargs)
        calls = getattr(HTTP_CAPTURE, "calls", None)
        if calls is not None:
            calls.append(
                {
                    "method": method,
                    "url": url,
                    "status": int(response.status_code),
                }
            )
        return response

    requests.Session.request = bounded
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")


def tool_files() -> list[Path]:
    return sorted(TOOL_ROOT.rglob("*.py"))


def function_info(path: Path) -> tuple[object, dict]:
    source = path.read_text(encoding="utf-8")
    match = re.search(r"^def\s+(\w+)\s*\(", source, re.MULTILINE)
    if not match:
        raise ValueError("no top-level function")
    spec = importlib.util.spec_from_file_location(f"doc2agent_{abs(hash(str(path)))}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, match.group(1))
    params = {
        name: sample for name, sample in REQUIRED_SAMPLES.items() if name in inspect.signature(func).parameters
    }
    return func, params


def payload_has_error(payload: object) -> bool:
    if isinstance(payload, dict):
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        return False
    for value in values:
        if isinstance(value, dict):
            if payload_has_error(value):
                return True
        elif isinstance(value, str):
            lowered = value.lower()
            if "exception" in lowered or "error occurred" in lowered:
                return True
    return False


def classify_response(status: int | None, response: object) -> str:
    if status is None:
        return "returned_without_http"
    if 200 <= status < 300:
        return "api_error" if payload_has_error(response) else "ok"
    if status in (400, 422):
        return "bad_request"
    if status in (401, 403):
        return "auth_required"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "server_error"
    return f"http_{status}"


def probe(path: Path) -> dict:
    relative = path.relative_to(TOOL_ROOT)
    group = relative.parts[0]
    source = path.read_text(encoding="utf-8")
    url_match = URL_RE.search(source)
    record = {
        "group": group,
        "tool": path.stem,
        "method": "POST" if path.stem.endswith("_POST") else "GET",
        "url": url_match.group(1) if url_match else "",
        "http_status": "",
        "http_chain": "",
        "class": "",
        "ms": "",
        "error": "",
        "self_reported_status": "",
    }
    HTTP_CAPTURE.calls = []
    try:
        func, kwargs = function_info(path)
        started = time.perf_counter()
        response = func(**kwargs)
        elapsed = (time.perf_counter() - started) * 1000
        calls = list(getattr(HTTP_CAPTURE, "calls", []))
        status = calls[-1]["status"] if calls else None
        if isinstance(response, dict) and "status_code" in response:
            record["self_reported_status"] = "yes"
        record["http_status"] = "" if status is None else status
        record["http_chain"] = " -> ".join(
            f"{call['method']} {call['status']}" for call in calls
        )
        record["ms"] = round(elapsed, 1)
        record["class"] = classify_response(status, response)
        try:
            response.close()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass
    except Exception as exc:  # noqa: BLE001 - one failing tool must not stop the sweep
        message = f"{type(exc).__name__}: {str(exc)[:160]}"
        name = type(exc).__name__
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            status = int(exc.response.status_code)
            record["http_status"] = status
            record["class"] = classify_response(status, None)
        elif name == "AssertionError" or "must be provided" in str(exc) or "Missing required" in str(exc):
            record["class"] = "param_error"
        elif name == "ImportError" or name == "ModuleNotFoundError":
            record["class"] = "dependency_missing"
        elif name in {"NameError", "TypeError"}:
            record["class"] = "wrapper_bug"
        elif name in {"Timeout", "TimeoutError"}:
            record["class"] = "timeout"
        elif name in {"ConnectionError", "SSLError", "ConnectTimeout"}:
            record["class"] = "unreachable"
        else:
            record["class"] = "error"
        record["error"] = message
    return record


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    patch_requests()
    paths = tool_files()
    rows = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(probe, p): p for p in paths}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda r: (r["group"], r["tool"]))

    fields = [
        "group",
        "tool",
        "method",
        "url",
        "http_status",
        "http_chain",
        "class",
        "ms",
        "error",
        "self_reported_status",
    ]
    with (OUT_DIR / "doc2agent_tools.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    alive = sum(counts.get(name, 0) for name in REACHABLE_CLASSES)
    broken = sum(counts.get(name, 0) for name in ("param_error", "wrapper_bug", "dependency_missing"))
    unreachable = sum(counts.get(name, 0) for name in ("unreachable", "timeout"))
    summary = {
        "total_tools": len(rows),
        "class_counts": dict(sorted(counts.items())),
        "directly_ok": counts.get("ok", 0),
        "self_reported_ok": sum(1 for row in rows if row["self_reported_status"] == "yes"),
        "service_alive": alive,
        "service_alive_rate": round(alive / len(rows), 4) if rows else 0.0,
        "unreachable": unreachable,
        "not_exercised": broken,
        "unaccounted": len(rows) - alive - unreachable - broken,
        "wrapper_or_param_broken": broken,
        "by_group": {},
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    for row in rows:
        bucket = summary["by_group"].setdefault(row["group"], {"total": 0, "ok": 0, "alive": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if row["class"] == "ok" else 0
        bucket["alive"] += 1 if row["class"] in REACHABLE_CLASSES else 0
    (OUT_DIR / "doc2agent_tools_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
