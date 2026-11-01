"""Retest the W2 Doc2Agent blockers with task-grounded arguments.

The W2 inventory used generic wrapper probes. That is useful for discovering
breakage, but it cannot separate an invalid probe from an upstream service
failure. This script replays the 17 blocked tools with task-derived arguments,
records a control probe where the task-required query is known to be too
specific, and emits one evidence row per tool.

The script calls public HTTP APIs. Unit tests exercise the classifier with
synthetic observations and do not make network requests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_W2_CSV = ROOT / "reports" / "w2_day2" / "tool_feasibility.csv"
DEFAULT_W2_SUMMARY = ROOT / "reports" / "w2_day2" / "tool_feasibility_summary.json"
DEFAULT_TOOLS_DIR = Path(
    os.environ.get(
        "DOC2AGENT_TOOLS_DIR",
        r"D:\wbworkspace\Doc2Agent\test_glycan\MCPTools",
    )
)
DEFAULT_OUT_CSV = ROOT / "reports" / "w2_day3" / "tool_blocker_recheck.csv"
DEFAULT_OUT_SUMMARY = (
    ROOT / "reports" / "w2_day3" / "tool_blocker_recheck_summary.json"
)
DEFAULT_OUT_TASK_CSV = (
    ROOT / "reports" / "w2_day3" / "task_feasibility_corrections.csv"
)
DEFAULT_OUT_TASK_FULL_CSV = (
    ROOT / "reports" / "w2_day3" / "task_feasibility_revised.csv"
)

PASS = "passes_with_valid_args"
API = "api_contract_failure"
SERVICE = "service_failure"
TLS = "tls_verification_failure"
DEPENDENCY = "local_dependency_missing"
WRAPPER = "local_wrapper_bug"
REDESIGN = "passes_but_task_needs_redesign"
CLASSES = (PASS, API, SERVICE, TLS, DEPENDENCY, WRAPPER, REDESIGN)

DIRECT = "current_tools_direct"
REPLACEMENT = "needs_replacement_tool"
W2_SERVICE = "service_failure"

WURCS = (
    "WURCS=2.0/3,5,4/[a2122h-1b_1-5_2*NCC/3=O][a1122h-1b_1-5]"
    "[a1122h-1a_1-5]/1-1-2-3-3/a4-b1_b4-c1_c3-d1_c6-e1"
)
GWS = (
    "freeEnd--?b1D-GlcNAc,p--4b1D-GlcNAc,p--4b1D-Man,p--?a1D-Man,p"
    "$MONO,Und,0,0,freeEnd"
)
COMPLEX_IUPAC = (
    "α-D-Manp-(1→3)[α-D-Manp-(1→6)]-β-D-Manp-(1→4)-"
    "β-D-GlcpNAc-(1→4)-β-D-GlcpNAc-(1→4)-β-D-Glcp-(1→O)Cer"
)
COMPLEX_COMPOSITION = "Neu5Ac(1)Hex(3)HexNAc(2)Fuc(1)"

TASK_CSV_FIELDS = (
    "task_id",
    "original_category",
    "revised_category",
    "blocking_tool",
    "original_class",
    "recheck_class",
    "reason",
    "evidence",
)
REVISED_TASK_FIELDS = (
    "task_id",
    "original_category",
    "revised_category",
    "blocking_tools",
    "original_classes",
    "recheck_classes",
    "decision_reason",
    "evidence",
)


@dataclass(frozen=True)
class ProbeSpec:
    tool: str
    source_tasks: tuple[int, ...]
    w2_classes: tuple[str, ...]
    args: dict[str, Any]
    probe_basis: str
    expected_kind: str
    task_fit: str
    task_impact: str
    attempts: int = 1
    control_args: dict[str, Any] | None = None
    control_expected_kind: str | None = None
    control_note: str = ""
    tls_bypass_url: str | None = None
    tls_bypass_params: dict[str, str] | None = None


@dataclass(frozen=True)
class TaskOverride:
    category: str
    reason: str


@dataclass
class ProbeObservation:
    tool: str
    probe_kind: str
    args: dict[str, Any]
    http_status: int | None
    elapsed_ms: int
    attempts_used: int
    request_url: str
    return_type: str
    response_summary: str
    error: str
    content_satisfied: bool
    content_note: str
    tls_bypass_status: int | None = None
    tls_bypass_note: str = ""


@dataclass
class ToolRecord:
    spec: ProbeSpec
    observation: ProbeObservation
    control: ProbeObservation | None
    recheck_class: str
    service_reachable: bool
    default_transport_ok: bool
    root_cause: str
    wrapper_file: str
    wrapper_sha256: str
    extra: dict[str, str] = field(default_factory=dict)


SPECS: tuple[ProbeSpec, ...] = (
    ProbeSpec(
        tool="compound_property_tables",
        source_tasks=(3, 13, 47),
        w2_classes=("param_error",),
        args={
            "cid": "2244,5957,7629",
            "property_tags": "MolecularFormula,MolecularWeight,InChIKey",
        },
        probe_basis="task 3 identifiers plus PubChem property names with required casing",
        expected_kind="compound_csv",
        task_fit="direct",
        task_impact="Property names are case-sensitive; task 13 used lowercase names.",
    ),
    ProbeSpec(
        tool="get_feature_by_locations",
        source_tasks=(6, 15),
        w2_classes=("bad_request",),
        args={
            "taxonomy": "9606",
            "locations": "1:450000-550000",
            "offset": 0,
            "size": 100,
            "in_range": True,
            "format": "json",
        },
        probe_basis="task 6 genomic location and documented coordinate syntax",
        expected_kind="json_2xx",
        task_fit="direct",
        task_impact="The valid chromosome form returns feature JSON; task 15 used an invalid chromosome name.",
        control_args={
            "taxonomy": "9606",
            "locations": "X:58205437-58219305",
            "offset": 0,
            "size": 100,
            "in_range": True,
            "format": "json",
        },
        control_note="Task 15's chromosome X range also returns a JSON-capable response.",
    ),
    ProbeSpec(
        tool="search_uniprot_entries_by_taxonomy_and_genomic_coordinates",
        source_tasks=(10,),
        w2_classes=("bad_request",),
        args={
            "taxonomy": "9606",
            "locations": "X:58205437-58219305",
            "offset": 0,
            "size": 100,
            "in_range": "true",
            "format": "json",
        },
        probe_basis="task 10 coordinates",
        expected_kind="json_2xx",
        task_fit="direct",
        task_impact="The endpoint accepts the task coordinates; an empty JSON list is a data result, not a transport failure.",
    ),
    ProbeSpec(
        tool="get_fungal_lectins",
        source_tasks=(12, 23),
        w2_classes=("bad_request",),
        args={
            "getcolumns": "fold,domain,species",
            "wherecolumn": "species",
            "isvalue": "Aspergillus niger",
            "limit": 100,
        },
        probe_basis="task 23 species and the wrapper's documented schema names",
        expected_kind="lectin_table",
        task_fit="direct",
        task_impact="The endpoint works when the model uses fold/domain/species instead of invented aliases.",
        control_args={
            "getcolumns": "fold,domain,species",
            "wherecolumn": "species",
            "isvalue": "Candida albicans",
            "limit": 100,
        },
        control_note="Task 12's Candida albicans query also returns a lectin table.",
    ),
    ProbeSpec(
        tool="get_trefoil_lectins",
        source_tasks=(14,),
        w2_classes=("param_error",),
        args={
            "getcolumns": "domain,uniprot,superkingdom",
            "wherecolumn": "superkingdom",
            "isvalue": "Bacteria",
            "limit": 2000,
        },
        probe_basis="task 14 fields, with the value separated from the column name",
        expected_kind="lectin_table",
        task_fit="direct",
        task_impact="The wrapper requires wherecolumn and isvalue separately; the task's SQL-like value caused the W2 probe error.",
    ),
    ProbeSpec(
        tool="generate_glycan_image",
        source_tasks=(16, 32, 34, 35, 42, 44),
        w2_classes=("param_error",),
        args={
            "format": "png",
            "type": "html",
            "wurcs": WURCS,
            "verify": True,
        },
        probe_basis="task 42's PNG output and the wrapper's documented html response type",
        expected_kind="image_html",
        task_fit="direct",
        task_impact="The wrapper works when format and response type are both valid; the model mixed those two fields.",
        control_args={
            "format": "svg",
            "type": "html",
            "wurcs": (
                "WURCS=2.0/3,5,4/[a1221h-1b_1-5_2*NCC/3=O]"
                "[a1122h-1b_1-5][a1122h-1a_1-5]/1-1-2-3-3/"
                "a4-b1_b4-c1_c3-d1_c6-e1"
            ),
            "verify": True,
        },
        control_note="Task 16's SVG branch also returns image markup.",
    ),
    ProbeSpec(
        tool="get_natural_variants_by_hgvs_expression",
        source_tasks=(18,),
        w2_classes=("bad_request",),
        args={
            "hgvs": "NC_000017.11:g.58223910G>A",
            "offset": 0,
            "size": 100,
            "sourcetype": "uniprot,clinvar",
            "consequencetype": "missense,stop gained",
        },
        probe_basis="task 18 HGVS expression",
        expected_kind="json_2xx",
        task_fit="direct",
        task_impact="The expected wrapper works with its own HGVS parameter; the model called a different search wrapper.",
    ),
    ProbeSpec(
        tool="convert_gws_format_to_wurcs_format",
        source_tasks=(11, 36),
        w2_classes=("api_error",),
        args={"gws": GWS},
        probe_basis="task 11 GWS string",
        expected_kind="gws_result",
        task_fit="direct",
        task_impact="The task input returns a structured WURCS record; the W2 generic probe did not exercise this contract.",
        control_args={
            "gws": (
                "freeEnd--?b1D-GlcNAc,p--3b1D-Gal,p--4b1D-Glc,p--"
                "6b1D-GlcNAc,p$MONO,Und,0,0,freeEnd"
            )
        },
        control_note="Task 36's GWS input also returns a structured WURCS record.",
    ),
    ProbeSpec(
        tool="get_human_lectome",
        source_tasks=(40,),
        w2_classes=("bad_request",),
        args={
            "getcolumns": "RefSeqID,UniProt_ID",
            "wherecolumn": "common_protein_name",
            "isvalue": "%SIGLEC%",
            "limit": 1000,
        },
        probe_basis="task 40 explicit arguments",
        expected_kind="lectin_table",
        task_fit="direct",
        task_impact="The task's own query returns a lectin table; the generic probe parameter set caused the earlier 400.",
    ),
    ProbeSpec(
        tool="get_predicted_lectins",
        source_tasks=(41,),
        w2_classes=("bad_request",),
        args={
            "getcolumns": "fold,domain,uniprot,superkingdom",
            "wherecolumn": "superkingdom",
            "isvalue": "Bacteria%",
            "limit": 10,
        },
        probe_basis="task 41 bacterial filter with the wrapper's documented schema",
        expected_kind="lectin_table",
        task_fit="direct",
        task_impact="The project runtime returns data; the earlier D:\\python probe also exposed a pandas dependency mismatch.",
    ),
    ProbeSpec(
        tool="get_ligands",
        source_tasks=(48,),
        w2_classes=("bad_request",),
        args={
            "getcolumns": "ligand_id,iupac",
            "wherecolumn": "iupac",
            "isvalue": "%Gal%",
            "limit": 100,
        },
        probe_basis="task 48 ligand-table fields with a minimally restrictive documented example",
        expected_kind="structured_response",
        task_fit="empty_result",
        task_impact="The service returns an empty array, so the tool is reachable but task 48 still lacks usable ligand data.",
    ),
    ProbeSpec(
        tool="convert_composition_to_wurcs",
        source_tasks=(31,),
        w2_classes=("server_error",),
        args={"composition": "Hex:4|HexNAc:4|Fuc:1"},
        probe_basis="task 31 exact composition",
        expected_kind="wurcs_text",
        task_fit="direct",
        attempts=3,
        task_impact="The task input returns WURCS; the W2 generic probe's HTTP 500 does not reproduce and task 31 is not service-failed.",
    ),
    ProbeSpec(
        tool="find",
        source_tasks=(28,),
        w2_classes=("wrapper_bug",),
        args={
            "database": "compound",
            "query": "flavonoids",
            "option": "exact_mass=286.2",
        },
        probe_basis="task 28's combined keyword and exact-mass request",
        expected_kind="kegg_lines",
        task_fit="requires_redesign",
        task_impact="KEGG supports keyword or exact-mass lookup, not both in one path; the task needs two queries or a replacement tool.",
        control_args={
            "database": "compound",
            "query": "286.2",
            "option": "exact_mass",
        },
        control_expected_kind="kegg_lines",
        control_note="Valid exact-mass lookup returns KEGG compound rows.",
    ),
    ProbeSpec(
        tool="get_lectins",
        source_tasks=(5, 50),
        w2_classes=("bad_request",),
        args={
            "getcolumns": "pdb,uniprot",
            "wherecolumn": "species",
            "isvalue": "Saccharomyces cerevisiae",
            "limit": 100,
        },
        probe_basis="task 50's PDB and UniProt fields",
        expected_kind="lectin_table",
        task_fit="blocked",
        task_impact="The PDB column still triggers an upstream ambiguous-column SQL error; non-PDB lectin queries work.",
        control_args={
            "getcolumns": "uniprot,fold,class",
            "wherecolumn": "species",
            "isvalue": "Homo sapiens",
            "limit": 5,
        },
        control_expected_kind="lectin_table",
        control_note="A control query without PDB returns a lectin table.",
    ),
    ProbeSpec(
        tool="convert_iupac_extended_to_wurcs",
        source_tasks=(1, 32),
        w2_classes=("api_error",),
        args={
            "iupacextended": (
                "α-D-Manp-(1→3)[α-D-Manp-(1→6)]-β-D-Manp-(1→4)-"
                "β-D-GlcpNAc-(1→4)-β-D-GlcpNAc-(1→"
            )
        },
        probe_basis="task 32 exact IUPAC Extended prefix",
        expected_kind="iupac_result",
        task_fit="direct",
        task_impact="Both task inputs return WURCS; task 1 has no accession, but its expected output is WURCS.",
        control_args={"iupacextended": COMPLEX_IUPAC},
        control_expected_kind="iupac_result",
        control_note="The full task 1 input also returns WURCS without a GlyTouCan accession.",
    ),
    ProbeSpec(
        tool="convert_composition_text_to_wurcs_format",
        source_tasks=(21, 37),
        w2_classes=("http_424",),
        args={"text": COMPLEX_COMPOSITION},
        probe_basis="task 21 and task 37 exact composition",
        expected_kind="wurcs_with_accession",
        task_fit="blocked",
        task_impact="Task 21 needs both WURCS and a GlyTouCan ID; task 37 needs WURCS only.",
        control_args={"text": "Hex(3)HexNAc(2)"},
        control_expected_kind="wurcs_with_accession",
        control_note="A standard composition returns both WURCS and a GlyTouCan accession.",
    ),
    ProbeSpec(
        tool="get_proteins",
        source_tasks=(20, 46),
        w2_classes=("unreachable",),
        args={"query_protein": "P08047"},
        probe_basis="task 20 exact UniProt accession",
        expected_kind="protein_json",
        task_fit="blocked",
        task_impact="The default wrapper still fails certificate verification. The service is alive, but disabling TLS verification is not a production fix.",
        tls_bypass_url="https://oglcnac.mcw.edu/api/v1/proteins/",
        tls_bypass_params={"query_protein": "P08047"},
    ),
)


TASK_OVERRIDES: dict[int, TaskOverride] = {
    21: TaskOverride(
        REPLACEMENT,
        "The exact composition returns WURCS but no GlyTouCan identifier, which task 21 asks for.",
    ),
    37: TaskOverride(
        DIRECT,
        "Task 37 needs WURCS only; its exact composition returns G14669DU and WURCS.",
    ),
    48: TaskOverride(
        REPLACEMENT,
        "The reachable ligand endpoint returned an empty list, so the task still lacks usable ligand data.",
    ),
}


_request_capture = threading.local()
_capture_enabled = False
_original_request = requests.Session.request


def _capturing_request(self, method, url, **kwargs):
    kwargs["timeout"] = min(float(kwargs.get("timeout") or 50), 50)
    response = _original_request(self, method, url, **kwargs)
    if _capture_enabled:
        calls = getattr(_request_capture, "calls", [])
        calls.append((method, url, int(response.status_code)))
        _request_capture.calls = calls
    return response


requests.Session.request = _capturing_request


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def find_wrapper_path(tool: str, tools_dir: Path) -> Path:
    for suffix in ("_GET.py", "_POST.py"):
        candidate = tools_dir / f"{tool}{suffix}"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No wrapper for {tool} under {tools_dir}")


def load_wrapper(tool: str, tools_dir: Path):
    path = find_wrapper_path(tool, tools_dir)
    module_name = f"doc2agent_recheck_{tool}_{sha256(path)[:10]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load wrapper {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, tool)


def safe_json(response: Any) -> Any:
    if isinstance(response, (dict, list)):
        return response
    try:
        return response.json()
    except Exception:
        return None


def response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text is not None:
        return str(text)
    if isinstance(response, (dict, list, str, int, float, bool)) or response is None:
        return json.dumps(response, ensure_ascii=False)
    return str(response)


def preview(value: Any, limit: int = 500) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    text = text.replace("\r", " ").replace("\n", " ")
    return text[:limit]


def has_wurcs(value: Any) -> bool:
    text = preview(value, 5000)
    return "WURCS=" in text or "'wurcs'" in text.lower() or '"wurcs"' in text.lower()


def content_satisfied(kind: str, response: Any, payload: Any) -> tuple[bool, str]:
    status = getattr(response, "status_code", 200)
    text = response_text(response).strip()
    if not 200 <= status < 300:
        return False, f"HTTP {status}"
    if kind == "json_2xx":
        return True, "HTTP 2xx JSON-capable response"
    if kind == "compound_csv":
        ok = "MolecularFormula" in text and "MolecularWeight" in text
        return ok, "PubChem CSV property table" if ok else "property table missing"
    if kind == "lectin_table":
        ok = isinstance(payload, list) and len(payload) >= 2
        return ok, "lectin table" if ok else "lectin table missing or empty"
    if kind == "image_html":
        lowered = text.lower()
        ok = "<img" in lowered or "data:image" in lowered or "<svg" in lowered
        return ok, "image HTML" if ok else "image markup missing"
    if kind == "gws_result":
        ok = isinstance(payload, list) and bool(payload) and has_wurcs(payload)
        return ok, "GWS conversion record" if ok else "WURCS record missing"
    if kind == "structured_response":
        ok = isinstance(payload, (list, dict))
        detail = f"structured {type(payload).__name__}, length={len(payload)}"
        return ok, detail
    if kind == "wurcs_text":
        ok = text.startswith("WURCS=") or has_wurcs(payload)
        return ok, "WURCS text" if ok else "WURCS text missing"
    if kind == "kegg_lines":
        ok = any(line.startswith("C") and "\t" in line for line in text.splitlines())
        return ok, "KEGG rows" if ok else "KEGG rows missing"
    if kind == "iupac_result":
        ok = isinstance(payload, (dict, list)) and bool(payload) and has_wurcs(payload)
        return ok, "IUPAC conversion result" if ok else "empty or non-WURCS IUPAC result"
    if kind == "wurcs_with_accession":
        first = payload[0] if isinstance(payload, list) and payload else payload
        ok = (
            isinstance(first, dict)
            and bool(first.get("wurcs") or first.get("WURCS"))
            and bool(first.get("id") or first.get("glytoucan_ac") or first.get("accession"))
        )
        return ok, "WURCS and accession" if ok else "WURCS or accession missing"
    if kind == "protein_json":
        ok = isinstance(payload, (dict, list)) and bool(payload)
        return ok, "protein JSON" if ok else "protein JSON missing"
    raise ValueError(f"Unknown expected content kind: {kind}")


def should_retry(observation: ProbeObservation) -> bool:
    if observation.http_status in {429, 500, 502, 503, 504}:
        return True
    lowered = observation.error.lower()
    return any(token in lowered for token in ("timeout", "connectionreseterror", "connectionerror"))


def invoke_once(
    spec: ProbeSpec,
    args: dict[str, Any],
    expected_kind: str,
    probe_kind: str,
    tools_dir: Path,
) -> ProbeObservation:
    global _capture_enabled
    _request_capture.calls = []
    _capture_enabled = True
    started = time.perf_counter()
    response = None
    error = ""
    try:
        response = load_wrapper(spec.tool, tools_dir)(**args)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        _capture_enabled = False
    calls = getattr(_request_capture, "calls", [])
    status = calls[-1][2] if calls else getattr(response, "status_code", None)
    url = calls[-1][1] if calls else ""
    payload = safe_json(response) if response is not None else None
    if response is None:
        satisfied, note = False, "no response returned"
    else:
        try:
            satisfied, note = content_satisfied(expected_kind, response, payload)
        except Exception as exc:
            satisfied, note = False, f"validator error: {type(exc).__name__}: {exc}"
    summary_value = payload if payload is not None else response_text(response)
    return ProbeObservation(
        tool=spec.tool,
        probe_kind=probe_kind,
        args=args,
        http_status=status,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        attempts_used=1,
        request_url=url,
        return_type=type(response).__name__ if response is not None else "",
        response_summary=preview(summary_value),
        error=error,
        content_satisfied=satisfied,
        content_note=note,
    )


def invoke_probe(
    spec: ProbeSpec,
    args: dict[str, Any],
    expected_kind: str,
    probe_kind: str,
    tools_dir: Path,
    attempts: int = 1,
) -> ProbeObservation:
    observation = None
    for attempt in range(1, attempts + 1):
        observation = invoke_once(spec, args, expected_kind, probe_kind, tools_dir)
        observation.attempts_used = attempt
        if not should_retry(observation) or attempt == attempts:
            break
        time.sleep(2)
    assert observation is not None
    return observation


def probe_tls_bypass(spec: ProbeSpec) -> tuple[int | None, str]:
    if not spec.tls_bypass_url:
        return None, ""
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        response = requests.get(
            spec.tls_bypass_url,
            params=spec.tls_bypass_params,
            timeout=50,
            verify=False,
        )
        payload = safe_json(response)
        valid = isinstance(payload, (dict, list)) and bool(payload)
        note = (
            f"verify=False HTTP {response.status_code}; "
            f"JSON={type(payload).__name__}; usable={str(valid).lower()}; "
            "diagnostic only"
        )
        return response.status_code, note
    except Exception as exc:
        return None, f"verify=False failed: {type(exc).__name__}: {str(exc)[:300]}"


def classify_observation(
    spec: ProbeSpec,
    observation: ProbeObservation,
    control: ProbeObservation | None,
) -> str:
    error = observation.error.lower()
    if "modulenotfounderror" in error or "importerror" in error:
        return DEPENDENCY
    if "certificate_verify_failed" in error or "certificate verify failed" in error:
        return TLS
    if any(token in error for token in ("timeout", "connectionerror", "connectionreseterror")):
        return SERVICE
    if observation.http_status is not None and observation.http_status >= 500:
        return SERVICE
    if observation.http_status == 424:
        return SERVICE
    if any(
        token in error
        for token in ("typeerror:", "nameerror:", "assertionerror:")
    ):
        return WRAPPER
    if (
        spec.task_fit == "requires_redesign"
        and control is not None
        and control.content_satisfied
    ):
        return REDESIGN
    if observation.http_status is not None and 400 <= observation.http_status < 500:
        return API
    if not observation.content_satisfied:
        return API
    return PASS


def root_cause(record_class: str, observation: ProbeObservation, control: ProbeObservation | None) -> str:
    if record_class == PASS:
        return observation.content_note
    if record_class == REDESIGN:
        return "task query is not expressible by the wrapper; the control probe passes"
    if record_class == TLS:
        return f"{observation.error}; {observation.tls_bypass_note}".strip("; ")
    if record_class == SERVICE:
        if observation.error:
            return observation.error
        return observation.response_summary or f"HTTP {observation.http_status}"
    if record_class == API:
        detail = observation.response_summary or observation.error or observation.content_note
        return detail[:500]
    if record_class == DEPENDENCY:
        return observation.error
    if record_class == WRAPPER:
        return observation.error
    return observation.content_note


def build_record(
    spec: ProbeSpec,
    observation: ProbeObservation,
    control: ProbeObservation | None,
    tools_dir: Path,
) -> ToolRecord:
    recheck_class = classify_observation(spec, observation, control)
    service_reachable = bool(
        observation.http_status is not None
        or observation.tls_bypass_status is not None
        or (control is not None and control.http_status is not None)
    )
    default_transport_ok = bool(
        observation.http_status is not None
        and observation.http_status < 500
        and "certificate_verify_failed" not in observation.error.lower()
    )
    wrapper_path = find_wrapper_path(spec.tool, tools_dir)
    return ToolRecord(
        spec=spec,
        observation=observation,
        control=control,
        recheck_class=recheck_class,
        service_reachable=service_reachable,
        default_transport_ok=default_transport_ok,
        root_cause=root_cause(recheck_class, observation, control),
        wrapper_file=relative(wrapper_path),
        wrapper_sha256=sha256(wrapper_path),
    )


def control_result(record: ToolRecord) -> str:
    if record.observation.tls_bypass_status is not None:
        return record.observation.tls_bypass_note
    if record.control is None:
        return ""
    result = (
        f"HTTP {record.control.http_status}; "
        f"content={str(record.control.content_satisfied).lower()}; "
        f"{record.control.content_note}"
    )
    if record.spec.control_note:
        result += f"; {record.spec.control_note}"
    return result


def record_to_row(record: ToolRecord) -> dict[str, str]:
    return {
        "tool": record.spec.tool,
        "source_tasks": ",".join(str(value) for value in record.spec.source_tasks),
        "w2_classes": "|".join(record.spec.w2_classes),
        "probe_basis": record.spec.probe_basis,
        "task_fit": record.spec.task_fit,
        "recheck_class": record.recheck_class,
        "http_status": "" if record.observation.http_status is None else str(record.observation.http_status),
        "service_reachable": str(record.service_reachable).lower(),
        "default_transport_ok": str(record.default_transport_ok).lower(),
        "content_satisfied": str(record.observation.content_satisfied).lower(),
        "elapsed_ms": str(record.observation.elapsed_ms),
        "attempts_used": str(record.observation.attempts_used),
        "request_url": record.observation.request_url,
        "response_summary": record.observation.response_summary,
        "root_cause": record.root_cause,
        "control_result": control_result(record),
        "task_impact": record.spec.task_impact,
        "wrapper_file": record.wrapper_file,
        "wrapper_sha256": record.wrapper_sha256,
    }


def revised_task_category(
    task_id: int,
    original: str,
    blocking_tools: list[str],
    classes: dict[str, str],
) -> tuple[str, str]:
    override = TASK_OVERRIDES.get(task_id)
    if override is not None:
        return override.category, override.reason
    if not blocking_tools:
        return DIRECT, "No expected wrapper blocked this task in W2."

    missing = [tool for tool in blocking_tools if tool not in classes]
    if missing:
        raise ValueError(f"Task {task_id} has unclassified blockers: {missing}")
    rechecks = [classes[tool] for tool in blocking_tools]
    if any(value in {SERVICE, TLS} for value in rechecks):
        return W2_SERVICE, "At least one blocker still fails at the transport or service layer."
    if all(value == PASS for value in rechecks):
        return DIRECT, "All expected blocker tools return usable content with task-grounded arguments."
    return REPLACEMENT, "At least one blocker still has an API, dependency, or task-contract mismatch."


def task_revision_rows(
    w2_csv: Path,
    classes: dict[str, str],
) -> list[dict[str, str]]:
    revisions: list[dict[str, str]] = []
    with w2_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            blockers = [
                value.strip()
                for value in row["blocking_tools"].split("|")
                if value.strip()
            ]
            revised, reason = revised_task_category(
                int(row["task_id"]),
                row["category"],
                blockers,
                classes,
            )
            revisions.append(
                {
                    "task_id": row["task_id"],
                    "original_category": row["category"],
                    "revised_category": revised,
                    "blocking_tools": " | ".join(blockers),
                    "original_classes": row["blocking_classes"],
                    "recheck_classes": " | ".join(classes[tool] for tool in blockers),
                    "decision_reason": reason,
                    "evidence": "reports/w2_day3/tool_blocker_recheck.csv",
                }
            )
    return revisions


def correction_rows(
    revisions: list[dict[str, str]],
) -> list[dict[str, str]]:
    corrections: list[dict[str, str]] = []
    for row in revisions:
        if row["original_category"] == row["revised_category"]:
            continue
        corrections.append(
            {
                "task_id": row["task_id"],
                "original_category": row["original_category"],
                "revised_category": row["revised_category"],
                "blocking_tool": row["blocking_tools"],
                "original_class": row["original_classes"],
                "recheck_class": row["recheck_classes"],
                "reason": row["decision_reason"],
                "evidence": row["evidence"],
            }
        )
    return corrections


def build_task_revisions(
    w2_csv: Path,
    records: list[ToolRecord],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    classes = {record.spec.tool: record.recheck_class for record in records}
    revisions = task_revision_rows(w2_csv, classes)
    return revisions, correction_rows(revisions)


def build_summary(
    records: list[ToolRecord],
    revisions: list[dict[str, str]],
    corrections: list[dict[str, str]],
    w2_csv: Path,
    w2_summary: Path,
) -> dict[str, Any]:
    if len(records) != 17:
        raise ValueError(f"Expected 17 blocked tools, got {len(records)}")
    tools = [record.spec.tool for record in records]
    if len(tools) != len(set(tools)):
        raise ValueError("Duplicate tools in recheck records")
    counts = Counter(record.recheck_class for record in records)
    if set(counts) - set(CLASSES):
        raise ValueError(f"Unexpected recheck classes: {set(counts) - set(CLASSES)}")

    if len(revisions) != 50:
        raise ValueError(f"Expected 50 task revisions, got {len(revisions)}")
    original_counts = Counter(row["original_category"] for row in revisions)
    revised_counts = Counter(row["revised_category"] for row in revisions)

    return {
        "status": "PASS",
        "scope": "tool-level recheck and task-level feasibility; not an answer-quality score",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_blocked_tools": len(records),
        "recheck_class_counts": dict(sorted(counts.items())),
        "service_reachable": sum(record.service_reachable for record in records),
        "default_transport_ok": sum(record.default_transport_ok for record in records),
        "task_fit_counts": dict(
            sorted(Counter(record.spec.task_fit for record in records).items())
        ),
        "probe_accepted_tools": [
            record.spec.tool
            for record in records
            if record.recheck_class in {PASS, REDESIGN}
        ],
        "probe_accepted_note": (
            "This is a probe-level list. It includes an empty-result tool and a "
            "task that needs query redesign. Use task_fit_counts and "
            "task_feasibility_revised.csv for task usability."
        ),
        "persistent_blockers": [
            {
                "tool": record.spec.tool,
                "class": record.recheck_class,
                "root_cause": record.root_cause,
            }
            for record in records
            if record.recheck_class not in {PASS, REDESIGN}
        ],
        "w2_task_reclassification": {
            "original_counts": {
                DIRECT: original_counts[DIRECT],
                REPLACEMENT: original_counts[REPLACEMENT],
                W2_SERVICE: original_counts[W2_SERVICE],
            },
            "revised_counts": {
                DIRECT: revised_counts[DIRECT],
                REPLACEMENT: revised_counts[REPLACEMENT],
                W2_SERVICE: revised_counts[W2_SERVICE],
            },
            "changed_tasks": len(corrections),
            "corrections": corrections,
        },
        "validation": {
            "unique_tools": len(set(tools)),
            "all_tools_classified": all(record.recheck_class in CLASSES for record in records),
            "unique_tasks": len({row["task_id"] for row in revisions}),
            "three_categories_only": set(revised_counts) == {
                DIRECT,
                REPLACEMENT,
                W2_SERVICE,
            },
            "task_total_preserved": sum(revised_counts.values()) == 50,
        },
        "sources": {
            relative(w2_csv): sha256(w2_csv),
            relative(w2_summary): sha256(w2_summary),
        },
    }


def write_outputs(
    records: list[ToolRecord],
    revisions: list[dict[str, str]],
    corrections: list[dict[str, str]],
    summary: dict[str, Any],
    out_csv: Path,
    out_summary: Path,
    out_task_csv: Path,
    out_task_full_csv: Path,
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = [record_to_row(record) for record in records]
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with out_task_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TASK_CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(corrections)
    with out_task_full_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVISED_TASK_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(revisions)
    out_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_live(tools_dir: Path) -> list[ToolRecord]:
    records: list[ToolRecord] = []
    for spec in SPECS:
        observation = invoke_probe(
            spec,
            spec.args,
            spec.expected_kind,
            "task_required",
            tools_dir,
            attempts=spec.attempts,
        )
        control = None
        if spec.control_args is not None:
            control = invoke_probe(
                spec,
                spec.control_args,
                spec.control_expected_kind or spec.expected_kind,
                "control",
                tools_dir,
            )
        if spec.tls_bypass_url:
            status, note = probe_tls_bypass(spec)
            observation.tls_bypass_status = status
            observation.tls_bypass_note = note
        record = build_record(spec, observation, control, tools_dir)
        records.append(record)
        print(
            f"{record.spec.tool}: {record.recheck_class} "
            f"http={record.observation.http_status} "
            f"content={record.observation.content_satisfied}"
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tools-dir", type=Path, default=DEFAULT_TOOLS_DIR)
    parser.add_argument("--w2-csv", type=Path, default=DEFAULT_W2_CSV)
    parser.add_argument("--w2-summary", type=Path, default=DEFAULT_W2_SUMMARY)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    parser.add_argument("--out-task-csv", type=Path, default=DEFAULT_OUT_TASK_CSV)
    parser.add_argument(
        "--out-task-full-csv",
        type=Path,
        default=DEFAULT_OUT_TASK_FULL_CSV,
    )
    args = parser.parse_args()

    records = run_live(args.tools_dir)
    revisions, corrections = build_task_revisions(args.w2_csv, records)
    summary = build_summary(
        records,
        revisions,
        corrections,
        args.w2_csv,
        args.w2_summary,
    )
    write_outputs(
        records,
        revisions,
        corrections,
        summary,
        args.out_csv,
        args.out_summary,
        args.out_task_csv,
        args.out_task_full_csv,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
