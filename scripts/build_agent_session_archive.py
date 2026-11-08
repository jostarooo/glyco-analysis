#!/usr/bin/env python3
"""Build a sanitized, evidence-linked archive of project AI sessions.

The archive is an editorial engineering record, not a raw transcript export.
Every quoted excerpt is read from AgentsView SQLite and anchored to a stable
message ordinal or tool result event. The generator is deterministic and its
``--check`` mode rejects stale output, hand edits, and high-confidence secret
patterns.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
DEFAULT_MESSAGE_CHARS = 1400
DEFAULT_TOOL_CHARS = 1200
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILE_RE = re.compile(r"^\d{2}-[a-z0-9][a-z0-9-]*\.md$")
EVIDENCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{2,63}$")


class ArchiveError(RuntimeError):
    """Raised when the archive plan or its evidence is not trustworthy."""


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str


REDACTION_RULES = (
    RedactionRule(
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
            r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED:PRIVATE_KEY]",
    ),
    RedactionRule(
        "SECRET_PLACEHOLDER",
        re.compile(r"\{\{(?:PASSWORD|SECRET|TOKEN|API_KEY)_[^}\r\n]+\}\}"),
        "[REDACTED:SECRET_PLACEHOLDER]",
    ),
    RedactionRule(
        "GITHUB_TOKEN",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        "[REDACTED:GITHUB_TOKEN]",
    ),
    RedactionRule(
        "API_KEY",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "[REDACTED:API_KEY]",
    ),
    RedactionRule(
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED:JWT]",
    ),
    RedactionRule(
        "BEARER_TOKEN",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
        "Bearer [REDACTED:BEARER_TOKEN]",
    ),
    RedactionRule(
        "AUTHORIZATION",
        re.compile(r"(?im)(\bAuthorization\s*[:=]\s*)[^\r\n]+"),
        r"\1[REDACTED:AUTHORIZATION]",
    ),
    RedactionRule(
        "COOKIE",
        re.compile(r"(?im)(\b(?:Cookie|Set-Cookie)\s*:\s*)[^\r\n]+"),
        r"\1[REDACTED:COOKIE]",
    ),
    RedactionRule(
        "PASSWORD",
        re.compile(
            r"(?i)(\b(?:password|passwd|pwd)\b\s*[:=]\s*)"
            r"(?!\[REDACTED:)(?:[\"'`][^\"'`\r\n]+[\"'`]|[^\s,;\"'`}\]]{3,})"
        ),
        r"\1[REDACTED:PASSWORD]",
    ),
    RedactionRule(
        "PASSWORD_CN",
        re.compile(
            r"(密码\s*(?:[:：=]\s*)?)(?!\[REDACTED:)"
            r"(?:`[^`\r\n]+`|[^\s，。；、`\r\n]{6,})"
        ),
        r"\1[REDACTED:PASSWORD]",
    ),
    RedactionRule(
        "CREDENTIAL_ASSIGNMENT",
        re.compile(
            r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|"
            r"github[_-]?token)\b\s*[:=]\s*)(?!\[REDACTED:)"
            r"(?:[\"'`][^\"'`\r\n]+[\"'`]|[^\s,;\"'`}\]]{6,})"
        ),
        r"\1[REDACTED:CREDENTIAL]",
    ),
    RedactionRule(
        "URL_TOKEN",
        re.compile(
            r"(?i)([?&](?:access_token|api_key|token|key)=)"
            r"(?!\[REDACTED:)([^&\s#]+)"
        ),
        r"\1[REDACTED:URL_TOKEN]",
    ),
    RedactionRule(
        "USER_HOME",
        re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+"),
        "%USERPROFILE%",
    ),
)


HIGH_CONFIDENCE_SECRETS = {
    "GitHub token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    "API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "JWT": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "Bearer token": re.compile(
        r"(?i)\bBearer\s+(?!\[REDACTED:)[A-Za-z0-9._~+/=-]{16,}"
    ),
    "private key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "Authorization header": re.compile(
        r"(?im)\bAuthorization\s*[:=]\s*(?!\[REDACTED:)\S+"
    ),
    "Cookie header": re.compile(
        r"(?im)\b(?:Cookie|Set-Cookie)\s*:\s*(?!\[REDACTED:)\S+"
    ),
    "password assignment": re.compile(
        r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*"
        r"(?!\[REDACTED:)(?:[\"'`][^\"'`\r\n]+[\"'`]|[^\s,;\"'`}\]]{8,})"
    ),
    "Chinese password": re.compile(
        r"密码\s*(?![:：=]?\s*\[REDACTED:)(?:[:：=]\s*)?"
        r"(?:`[^`\r\n]{6,}`|[^\s，。；、`\r\n]{6,})"
    ),
    "credential assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|"
        r"github[_-]?token)\b\s*[:=]\s*(?!\[REDACTED:)"
        r"(?:[\"'`][^\"'`\r\n]+[\"'`]|[^\s,;\"'`}\]]{6,})"
    ),
    "URL token": re.compile(
        r"(?i)[?&](?:access_token|api_key|token|key)="
        r"(?!\[REDACTED:)[^&\s#]+"
    ),
}


@dataclass(frozen=True)
class SessionSpec:
    session_id: str
    label: str
    verify_source_file: bool
    volatile_reason: str = ""


@dataclass(frozen=True)
class SessionSource:
    spec: SessionSpec
    project: str
    agent: str
    started_at: str
    ended_at: str
    message_count: int
    file_path: str
    file_size: int
    db_file_hash: str
    actual_file_hash: str
    secret_leak_count: int
    transcript_fidelity: str
    is_truncated: int


@dataclass(frozen=True)
class EvidenceSpec:
    evidence_id: str
    kind: str
    session_id: str
    ordinal: int
    label: str
    call_index: int | None = None
    event_index: int | None = None
    excerpt_chars: int | None = None


@dataclass(frozen=True)
class Paragraph:
    text: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    heading: str
    paragraphs: tuple[Paragraph, ...]


@dataclass(frozen=True)
class RecordSpec:
    date: str
    file_name: str
    title: str
    summary: str
    summary_evidence: tuple[str, ...]
    sections: tuple[Section, ...]
    boundaries: tuple[Paragraph, ...]
    ai_use: tuple[Paragraph, ...]
    evidence: tuple[EvidenceSpec, ...]


@dataclass(frozen=True)
class Plan:
    raw: dict[str, Any]
    sessions: dict[str, SessionSpec]
    records: tuple[RecordSpec, ...]


@dataclass(frozen=True)
class EvidenceRecord:
    spec: EvidenceSpec
    role_or_tool: str
    source_locator: str
    raw_sha256: str
    excerpt: str
    redactions: dict[str, int]


@dataclass
class BuildResult:
    outputs: dict[str, bytes]
    evidence: dict[str, EvidenceRecord]
    sources: dict[str, SessionSource]
    record_hashes: dict[str, str] = field(default_factory=dict)
    redaction_counts: dict[str, int] = field(default_factory=dict)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ArchiveError(f"缺少归档计划：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"归档计划不是合法 JSON：{exc}") from exc


def _require_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArchiveError(f"{where} 必须是非空字符串")
    return value.strip()


def _require_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise ArchiveError(f"{where} 必须是布尔值")
    return value


def _require_int(value: Any, where: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ArchiveError(f"{where} 必须是大于等于 {minimum} 的整数")
    return value


def _parse_paragraphs(value: Any, where: str) -> tuple[Paragraph, ...]:
    if not isinstance(value, list) or not value:
        raise ArchiveError(f"{where} 必须是非空数组")
    paragraphs: list[Paragraph] = []
    for index, item in enumerate(value):
        prefix = f"{where}[{index}]"
        if not isinstance(item, dict):
            raise ArchiveError(f"{prefix} 必须是对象")
        text = _require_str(item.get("text"), f"{prefix}.text")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ArchiveError(f"{prefix}.evidence 必须是非空数组")
        refs = tuple(
            _require_str(ref, f"{prefix}.evidence[{ref_index}]")
            for ref_index, ref in enumerate(evidence)
        )
        if len(refs) != len(set(refs)):
            raise ArchiveError(f"{prefix}.evidence 不能重复")
        paragraphs.append(Paragraph(text=text, evidence=refs))
    return tuple(paragraphs)


def parse_plan(raw: dict[str, Any]) -> Plan:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ArchiveError(
            f"schema_version 必须是 {SCHEMA_VERSION}，实际为 {raw.get('schema_version')!r}"
        )

    sessions_raw = raw.get("sessions")
    if not isinstance(sessions_raw, list) or not sessions_raw:
        raise ArchiveError("sessions 必须是非空数组")
    sessions: dict[str, SessionSpec] = {}
    for index, item in enumerate(sessions_raw):
        where = f"sessions[{index}]"
        if not isinstance(item, dict):
            raise ArchiveError(f"{where} 必须是对象")
        session_id = _require_str(item.get("id"), f"{where}.id")
        if not session_id.startswith("codex:"):
            raise ArchiveError(f"{where}.id 必须是 codex 会话 ID")
        if session_id in sessions:
            raise ArchiveError(f"重复会话：{session_id}")
        verify = _require_bool(
            item.get("verify_source_file"), f"{where}.verify_source_file"
        )
        volatile_reason = str(item.get("volatile_reason", "")).strip()
        if not verify and not volatile_reason:
            raise ArchiveError(
                f"{where} 不校验源文件时必须写明 volatile_reason"
            )
        sessions[session_id] = SessionSpec(
            session_id=session_id,
            label=_require_str(item.get("label"), f"{where}.label"),
            verify_source_file=verify,
            volatile_reason=volatile_reason,
        )

    records_raw = raw.get("records")
    if not isinstance(records_raw, list) or not records_raw:
        raise ArchiveError("records 必须是非空数组")
    records: list[RecordSpec] = []
    seen_evidence: set[str] = set()
    seen_files: set[str] = set()
    for record_index, item in enumerate(records_raw):
        where = f"records[{record_index}]"
        if not isinstance(item, dict):
            raise ArchiveError(f"{where} 必须是对象")
        date = _require_str(item.get("date"), f"{where}.date")
        if not DATE_RE.fullmatch(date):
            raise ArchiveError(f"{where}.date 必须为 YYYY-MM-DD")
        file_name = _require_str(item.get("file"), f"{where}.file")
        if not FILE_RE.fullmatch(file_name):
            raise ArchiveError(
                f"{where}.file 必须匹配 NN-lowercase-slug.md"
            )
        logical_path = f"{date}/{file_name}"
        if logical_path in seen_files:
            raise ArchiveError(f"重复归档文件：{logical_path}")
        seen_files.add(logical_path)

        sections_raw = item.get("sections")
        if not isinstance(sections_raw, list) or not sections_raw:
            raise ArchiveError(f"{where}.sections 必须是非空数组")
        sections: list[Section] = []
        for section_index, section_raw in enumerate(sections_raw):
            section_where = f"{where}.sections[{section_index}]"
            if not isinstance(section_raw, dict):
                raise ArchiveError(f"{section_where} 必须是对象")
            sections.append(
                Section(
                    heading=_require_str(
                        section_raw.get("heading"), f"{section_where}.heading"
                    ),
                    paragraphs=_parse_paragraphs(
                        section_raw.get("paragraphs"),
                        f"{section_where}.paragraphs",
                    ),
                )
            )

        evidence_raw = item.get("evidence")
        if not isinstance(evidence_raw, list) or not evidence_raw:
            raise ArchiveError(f"{where}.evidence 必须是非空数组")
        evidence: list[EvidenceSpec] = []
        local_ids: set[str] = set()
        for evidence_index, evidence_item in enumerate(evidence_raw):
            evidence_where = f"{where}.evidence[{evidence_index}]"
            if not isinstance(evidence_item, dict):
                raise ArchiveError(f"{evidence_where} 必须是对象")
            evidence_id = _require_str(
                evidence_item.get("id"), f"{evidence_where}.id"
            )
            if not EVIDENCE_ID_RE.fullmatch(evidence_id):
                raise ArchiveError(
                    f"{evidence_where}.id 必须为大写字母、数字、下划线或短横线"
                )
            if evidence_id in seen_evidence or evidence_id in local_ids:
                raise ArchiveError(f"重复证据 ID：{evidence_id}")
            seen_evidence.add(evidence_id)
            local_ids.add(evidence_id)

            kind = _require_str(
                evidence_item.get("type"), f"{evidence_where}.type"
            )
            if kind not in {"message", "tool"}:
                raise ArchiveError(f"{evidence_where}.type 只能是 message 或 tool")
            session_id = _require_str(
                evidence_item.get("session"), f"{evidence_where}.session"
            )
            if session_id not in sessions:
                raise ArchiveError(
                    f"{evidence_where} 引用了未声明会话：{session_id}"
                )
            ordinal = _require_int(
                evidence_item.get("ordinal"),
                f"{evidence_where}.ordinal",
                minimum=0,
            )
            call_index = evidence_item.get("call_index")
            event_index = evidence_item.get("event_index")
            if kind == "tool":
                call_index = _require_int(
                    call_index, f"{evidence_where}.call_index", minimum=0
                )
                event_index = _require_int(
                    event_index, f"{evidence_where}.event_index", minimum=0
                )
            else:
                if call_index is not None or event_index is not None:
                    raise ArchiveError(
                        f"{evidence_where} 为 message 时不能设置 call_index/event_index"
                    )
            excerpt_chars = evidence_item.get("excerpt_chars")
            if excerpt_chars is not None:
                excerpt_chars = _require_int(
                    excerpt_chars,
                    f"{evidence_where}.excerpt_chars",
                    minimum=120,
                )
            evidence.append(
                EvidenceSpec(
                    evidence_id=evidence_id,
                    kind=kind,
                    session_id=session_id,
                    ordinal=ordinal,
                    label=_require_str(
                        evidence_item.get("label"), f"{evidence_where}.label"
                    ),
                    call_index=call_index,
                    event_index=event_index,
                    excerpt_chars=excerpt_chars,
                )
            )

        summary_evidence_raw = item.get("summary_evidence")
        if (
            not isinstance(summary_evidence_raw, list)
            or not summary_evidence_raw
        ):
            raise ArchiveError(f"{where}.summary_evidence 必须是非空数组")
        summary_evidence = tuple(
            _require_str(ref, f"{where}.summary_evidence[{ref_index}]")
            for ref_index, ref in enumerate(summary_evidence_raw)
        )

        record = RecordSpec(
            date=date,
            file_name=file_name,
            title=_require_str(item.get("title"), f"{where}.title"),
            summary=_require_str(item.get("summary"), f"{where}.summary"),
            summary_evidence=summary_evidence,
            sections=tuple(sections),
            boundaries=_parse_paragraphs(
                item.get("boundaries"), f"{where}.boundaries"
            ),
            ai_use=_parse_paragraphs(item.get("ai_use"), f"{where}.ai_use"),
            evidence=tuple(evidence),
        )

        referenced = set(summary_evidence)
        for section in record.sections:
            for paragraph in section.paragraphs:
                referenced.update(paragraph.evidence)
        for paragraph in record.boundaries + record.ai_use:
            referenced.update(paragraph.evidence)
        unknown = referenced - local_ids
        if unknown:
            raise ArchiveError(
                f"{logical_path} 引用了不存在的证据：{sorted(unknown)}"
            )
        unused = local_ids - referenced
        if unused:
            raise ArchiveError(
                f"{logical_path} 存在未被叙述引用的证据：{sorted(unused)}"
            )
        records.append(record)

    records.sort(key=lambda value: (value.date, value.file_name))
    return Plan(raw=raw, sessions=sessions, records=tuple(records))


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    result = text
    for rule in REDACTION_RULES:
        result, count = rule.pattern.subn(rule.replacement, result)
        if count:
            counts[rule.name] = count
    return result, counts


def find_sensitive_text(text: str) -> list[str]:
    findings: list[str] = []
    for label, pattern in HIGH_CONFIDENCE_SECRETS.items():
        if pattern.search(text):
            findings.append(label)
    return findings


def merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def open_readonly_db(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ArchiveError(f"AgentsView 数据库不存在：{path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
    except sqlite3.Error as exc:
        raise ArchiveError(f"无法只读打开 AgentsView 数据库：{exc}") from exc
    return connection


def load_sessions(
    connection: sqlite3.Connection,
    plan: Plan,
) -> dict[str, SessionSource]:
    sources: dict[str, SessionSource] = {}
    query = """
        SELECT id, project, agent, started_at, ended_at, message_count,
               file_path, file_size, file_hash, secret_leak_count,
               transcript_fidelity, is_truncated
        FROM sessions
        WHERE id = ?
    """
    for session_id, spec in plan.sessions.items():
        row = connection.execute(query, (session_id,)).fetchone()
        if row is None:
            raise ArchiveError(f"会话不存在：{session_id}")
        finding_count = connection.execute(
            "SELECT COUNT(*) FROM secret_findings WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        if finding_count or int(row["secret_leak_count"] or 0):
            raise ArchiveError(
                f"会话 {session_id} 仍含 {max(finding_count, int(row['secret_leak_count'] or 0))} 条疑似密钥"
            )
        if int(row["is_truncated"] or 0):
            raise ArchiveError(f"会话 {session_id} 的源记录已截断")
        if not row["file_hash"]:
            raise ArchiveError(f"会话 {session_id} 缺少源文件 SHA256")

        actual_hash = ""
        if spec.verify_source_file:
            raw_path = Path(row["file_path"] or "")
            if not row["file_path"] or not raw_path.is_file():
                raise ArchiveError(f"会话 {session_id} 的源文件不存在")
            raw_bytes = raw_path.read_bytes()
            actual_hash = sha256_bytes(raw_bytes)
            if int(row["file_size"] or -1) != len(raw_bytes):
                raise ArchiveError(f"会话 {session_id} 的源文件大小与数据库不一致")
            if actual_hash != row["file_hash"]:
                raise ArchiveError(f"会话 {session_id} 的源文件 SHA256 与数据库不一致")

        sources[session_id] = SessionSource(
            spec=spec,
            project=str(row["project"] or ""),
            agent=str(row["agent"] or ""),
            started_at=str(row["started_at"] or ""),
            ended_at=str(row["ended_at"] or ""),
            message_count=int(row["message_count"] or 0),
            file_path=str(row["file_path"] or ""),
            file_size=int(row["file_size"] or 0),
            db_file_hash=str(row["file_hash"]),
            actual_file_hash=actual_hash,
            secret_leak_count=int(row["secret_leak_count"] or 0),
            transcript_fidelity=str(row["transcript_fidelity"] or ""),
            is_truncated=int(row["is_truncated"] or 0),
        )
    return sources


def _truncate_text(value: str, limit: int) -> str:
    clean = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n\n... [证据摘录已按固定长度截断]"


def _message_evidence(
    connection: sqlite3.Connection,
    spec: EvidenceSpec,
) -> EvidenceRecord:
    row = connection.execute(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = ? AND ordinal = ?
        """,
        (spec.session_id, spec.ordinal),
    ).fetchone()
    if row is None:
        raise ArchiveError(
            f"缺少消息证据：{spec.session_id} ordinal={spec.ordinal}"
        )
    raw = {
        "session_id": spec.session_id,
        "ordinal": spec.ordinal,
        "role": row["role"],
        "content": row["content"],
    }
    excerpt, counts = redact_text(
        _truncate_text(
            str(row["content"]),
            spec.excerpt_chars or DEFAULT_MESSAGE_CHARS,
        )
    )
    return EvidenceRecord(
        spec=spec,
        role_or_tool=str(row["role"]),
        source_locator=f"ordinal={spec.ordinal}",
        raw_sha256=sha256_text(canonical_json(raw)),
        excerpt=excerpt,
        redactions=counts,
    )


def _tool_evidence(
    connection: sqlite3.Connection,
    spec: EvidenceSpec,
) -> EvidenceRecord:
    message = connection.execute(
        "SELECT id FROM messages WHERE session_id = ? AND ordinal = ?",
        (spec.session_id, spec.ordinal),
    ).fetchone()
    if message is None:
        raise ArchiveError(
            f"缺少工具调用所在消息：{spec.session_id} ordinal={spec.ordinal}"
        )
    call = connection.execute(
        """
        SELECT tool_name, input_json
        FROM tool_calls
        WHERE session_id = ? AND message_id = ? AND call_index = ?
        """,
        (spec.session_id, message["id"], spec.call_index),
    ).fetchone()
    if call is None:
        raise ArchiveError(
            "缺少工具调用："
            f"{spec.session_id} ordinal={spec.ordinal} call_index={spec.call_index}"
        )
    event = connection.execute(
        """
        SELECT status, content
        FROM tool_result_events
        WHERE session_id = ?
          AND tool_call_message_ordinal = ?
          AND call_index = ?
          AND event_index = ?
        """,
        (spec.session_id, spec.ordinal, spec.call_index, spec.event_index),
    ).fetchone()
    if event is None:
        raise ArchiveError(
            "缺少工具结果："
            f"{spec.session_id} ordinal={spec.ordinal} "
            f"call_index={spec.call_index} event_index={spec.event_index}"
        )
    raw = {
        "session_id": spec.session_id,
        "message_ordinal": spec.ordinal,
        "call_index": spec.call_index,
        "event_index": spec.event_index,
        "tool_name": call["tool_name"],
        "input_json": call["input_json"],
        "status": event["status"],
        "content": event["content"],
    }
    input_view = str(call["input_json"] or "(空)")
    try:
        parsed_input = json.loads(call["input_json"] or "null")
    except json.JSONDecodeError:
        parsed_input = None
    if isinstance(parsed_input, dict):
        if isinstance(parsed_input.get("cmd"), str):
            input_view = parsed_input["cmd"]
        else:
            input_view = json.dumps(
                parsed_input,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
    result_view = str(event["content"] or "(空)")
    normalized_result = result_view.replace("\r\n", "\n").replace("\r", "\n")
    result_lines = []
    for line in normalized_result.splitlines():
        if line.startswith(
            ("Chunk ID:", "Wall time:", "Original token count:", "Output:")
        ):
            continue
        result_lines.append(line)
    result_view = "\n".join(result_lines).strip() or "(空)"
    combined = (
        f"工具：{call['tool_name']}\n"
        f"状态：{event['status'] or '(未标记)'}\n\n"
        "参数：\n"
        f"{input_view}\n\n"
        "结果：\n"
        f"{result_view}"
    )
    excerpt, counts = redact_text(
        _truncate_text(combined, spec.excerpt_chars or DEFAULT_TOOL_CHARS)
    )
    return EvidenceRecord(
        spec=spec,
        role_or_tool=str(call["tool_name"]),
        source_locator=(
            f"ordinal={spec.ordinal}; "
            f"call_index={spec.call_index}; event_index={spec.event_index}"
        ),
        raw_sha256=sha256_text(canonical_json(raw)),
        excerpt=excerpt,
        redactions=counts,
    )


def load_evidence(
    connection: sqlite3.Connection,
    plan: Plan,
) -> dict[str, EvidenceRecord]:
    evidence: dict[str, EvidenceRecord] = {}
    for record in plan.records:
        for spec in record.evidence:
            if spec.kind == "message":
                item = _message_evidence(connection, spec)
            else:
                item = _tool_evidence(connection, spec)
            evidence[spec.evidence_id] = item
    return evidence


def _citation(refs: Iterable[str]) -> str:
    return " ".join(f"[{ref}]" for ref in refs)


def _render_paragraphs(paragraphs: Sequence[Paragraph]) -> list[str]:
    lines: list[str] = []
    for paragraph in paragraphs:
        lines.append(f"{paragraph.text} {_citation(paragraph.evidence)}")
        lines.append("")
    return lines


def _redaction_text(counts: dict[str, int]) -> str:
    if not counts:
        return "无"
    return "、".join(f"{key} {counts[key]} 次" for key in sorted(counts))


def render_record(
    record: RecordSpec,
    evidence: dict[str, EvidenceRecord],
    sources: dict[str, SessionSource],
) -> tuple[str, dict[str, int]]:
    lines = [
        f"# {record.title}",
        "",
        f"- 归档日期：`{record.date}`",
        "- 文档性质：由真实 AI 编程会话汇编的脱敏工程记录，不是原始聊天，也不是本人日志总结",
        f"- 会话数量：{len({spec.session_id for spec in record.evidence})}",
        f"- 证据数量：{len(record.evidence)}",
        "",
        "> 每条叙述都绑定真实消息或工具事件。证据摘录只保留与工程判断有关的部分，隐藏推理、无关上下文和敏感字段。",
        "",
        "## 摘要",
        "",
        f"{record.summary} {_citation(record.summary_evidence)}",
        "",
    ]
    total_redactions: dict[str, int] = {}
    for index, section in enumerate(record.sections, start=1):
        lines.extend([f"## {index}. {section.heading}", ""])
        lines.extend(_render_paragraphs(section.paragraphs))
    lines.extend(["## 判定边界", ""])
    lines.extend(_render_paragraphs(record.boundaries))
    lines.extend(["## AI 使用声明", ""])
    lines.extend(_render_paragraphs(record.ai_use))

    lines.extend(
        [
            "## 证据索引",
            "",
            "| 证据 | 类型 | 会话 | 原始定位 | 原始证据 SHA256 | 说明 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for spec in record.evidence:
        item = evidence[spec.evidence_id]
        merge_counts(total_redactions, item.redactions)
        lines.append(
            "| "
            f"`{spec.evidence_id}` | {spec.kind} | `{spec.session_id}` | "
            f"`{item.source_locator}` | `{item.raw_sha256}` | {spec.label} |"
        )
    lines.append("")

    lines.extend(["## 脱敏证据摘录", ""])
    for spec in record.evidence:
        item = evidence[spec.evidence_id]
        source = sources[spec.session_id]
        lines.extend(
            [
                f"### `{spec.evidence_id}` {spec.label}",
                "",
                f"- 会话：`{spec.session_id}`（{source.spec.label}）",
                f"- 类型：`{spec.kind}` / `{item.role_or_tool}`",
                f"- 定位：`{item.source_locator}`",
                f"- 原始证据 SHA256：`{item.raw_sha256}`",
                f"- 本摘录脱敏：{_redaction_text(item.redactions)}",
                "",
                "```text",
                item.excerpt,
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n", total_redactions


def render_daily_readme(
    date: str,
    records: Sequence[RecordSpec],
    record_hashes: dict[str, str],
    evidence: dict[str, EvidenceRecord],
    sources: dict[str, SessionSource],
) -> str:
    session_ids = sorted(
        {
            spec.session_id
            for record in records
            for spec in record.evidence
        }
    )
    lines = [
        f"# {date} AI 工程会话归档",
        "",
        "本页只汇总与本项目直接相关的真实 AI 编程会话。它用于审计问题定位、方案选择、命令证据和验证结果，不替代本人日志总结。",
        "",
        "## 当日记录",
        "",
        "| 文件 | 标题 | 证据数 | SHA256 |",
        "|---|---|---:|---|",
    ]
    for record in records:
        relative = f"{record.date}/{record.file_name}"
        lines.append(
            f"| [{record.file_name}]({record.file_name}) | {record.title} | "
            f"{len(record.evidence)} | `{record_hashes[relative]}` |"
        )
    lines.extend(
        [
            "",
            "## 会话来源",
            "",
            "| 会话 | 说明 | 源文件校验 |",
            "|---|---|---|",
        ]
    )
    for session_id in session_ids:
        source = sources[session_id]
        mode = (
            f"稳定 SHA256 `{source.actual_file_hash}`"
            if source.spec.verify_source_file
            else f"仅证据行哈希（{source.spec.volatile_reason}）"
        )
        lines.append(
            f"| `{session_id}` | {source.spec.label} | {mode} |"
        )
    lines.extend(
        [
            "",
            "## 计数",
            "",
            f"- 工程记录：{len(records)} 篇",
            f"- 会话：{len(session_ids)} 个",
            f"- 证据：{sum(len(record.evidence) for record in records)} 条",
            "",
        ]
    )
    return "\n".join(lines)


def render_index(
    plan: Plan,
    record_hashes: dict[str, str],
    evidence: dict[str, EvidenceRecord],
    sources: dict[str, SessionSource],
) -> str:
    lines = [
        "# AI 工程会话归档索引",
        "",
        "本索引汇总本项目真实 AI 编程会话的脱敏工程记录。所有摘录可回溯到会话 ID、消息序号或工具事件序号，并附原始证据哈希。",
        "",
        "## 记录",
        "",
        "| 日期 | 记录 | 标题 | 证据数 | SHA256 |",
        "|---|---|---|---:|---|",
    ]
    for record in plan.records:
        relative = f"{record.date}/{record.file_name}"
        lines.append(
            f"| {record.date} | [{record.file_name}]({relative}) | "
            f"{record.title} | {len(record.evidence)} | `{record_hashes[relative]}` |"
        )
    lines.extend(
        [
            "",
            "## 会话清单",
            "",
            "| 会话 | 说明 | 项目 | 开始时间 | 源文件策略 |",
            "|---|---|---|---|---|",
        ]
    )
    for session_id in sorted(sources):
        source = sources[session_id]
        policy = (
            f"源文件 SHA256 `{source.actual_file_hash}`"
            if source.spec.verify_source_file
            else f"只校验选定证据；{source.spec.volatile_reason}"
        )
        lines.append(
            f"| `{session_id}` | {source.spec.label} | `{source.project}` | "
            f"`{source.started_at}` | {policy} |"
        )
    lines.extend(
        [
            "",
            "## 统计",
            "",
            f"- 工程记录：{len(plan.records)} 篇",
            f"- 会话：{len(sources)} 个",
            f"- 证据：{len(evidence)} 条",
            "- 原始大型 JSONL：未上传",
            "- 隐藏推理、thinking_text：未导出",
            "",
            "## 复现",
            "",
            "```powershell",
            "$env:PYTHONUTF8='1'",
            "D:\\python\\python.exe scripts\\build_agent_session_archive.py `",
            "  --db D:\\AppData\\agentsview\\sessions.db `",
            "  --plan agent-sessions\\archive-plan.json `",
            "  --out agent-sessions",
            "",
            "D:\\python\\python.exe scripts\\build_agent_session_archive.py `",
            "  --db D:\\AppData\\agentsview\\sessions.db `",
            "  --plan agent-sessions\\archive-plan.json `",
            "  --out agent-sessions --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_readme(plan: Plan) -> str:
    return "\n".join(
        [
            "# AI 工程会话归档",
            "",
            "本目录保存与毕设糖基化分析系统直接相关的真实 AI 编程会话工程记录。记录来源是 Codex 会话在 AgentsView 中的结构化数据，不是手工编写的进度摘要。",
            "",
            "## 归档原则",
            "",
            "- 只归档本项目会话，不提交其他课程、私人项目或无关上下文。",
            "- 不提交原始大型 JSONL。当前主会话超过 100 MB，且会持续变化。",
            "- 不导出隐藏推理或 thinking_text，只保留用户目标、助手结论、命令和工具结果。",
            "- 每条证据绑定 `session_id`、消息 `ordinal`；工具证据另绑定 `call_index` 和 `event_index`。",
            "- 叙述是脱敏工程整理，不伪造原聊天、成功结果、命令或模型输出。",
            "- 提交前统一替换 token、Cookie、Authorization、密码、私钥、URL token 和用户主目录。",
            "",
            "## 目录结构",
            "",
            "```text",
            "agent-sessions/",
            "├─ README.md",
            "├─ INDEX.md",
            "├─ archive-plan.json",
            "├─ SOURCES.sha256",
            "└─ YYYY-MM-DD/",
            "   ├─ README.md",
            "   └─ NN-topic.md",
            "```",
            "",
            "## 可信度边界",
            "",
            "- 证据哈希证明当前数据库中的选定原文没有变化，不等同于模型回答一定正确。",
            "- 工程记录中的结论必须同时指向真实工具结果或项目产物。",
            "- 本目录不替代周进度报告、本人手写日志总结或周视频。",
            "- 主会话仍在增长时，不记录易变的整文件哈希，只记录选定证据的规范化行哈希。",
            "",
            "## 维护方式",
            "",
            "归档计划和证据选择写在 `archive-plan.json`。生成器与 `--check` 共用同一构建流程；连续运行不改变字节或 mtime，手改生成文件、缺失证据或疑似密钥残留都会失败。",
            "",
            f"当前包含 {len(plan.records)} 篇工程记录。完整入口见 [INDEX.md](INDEX.md)。",
            "",
        ]
    )


def render_sources(
    plan_path: Path,
    plan: Plan,
    evidence: dict[str, EvidenceRecord],
    sources: dict[str, SessionSource],
) -> str:
    lines = [
        f"{sha256_bytes(plan_path.read_bytes())}  archive-plan.json",
    ]
    for session_id in sorted(sources):
        source = sources[session_id]
        if source.spec.verify_source_file:
            lines.append(
                f"{source.actual_file_hash}  source-file/{session_id}"
            )
    for evidence_id in sorted(evidence):
        item = evidence[evidence_id]
        lines.append(
            f"{item.raw_sha256}  evidence/{evidence_id}  "
            f"{item.spec.session_id}#{item.source_locator}"
        )
    return "\n".join(lines) + "\n"


def build_archive(
    db_path: Path,
    plan_path: Path,
    out_dir: Path,
) -> BuildResult:
    raw_plan = read_json(plan_path)
    plan = parse_plan(raw_plan)
    plan_text = plan_path.read_text(encoding="utf-8-sig")
    plan_findings = find_sensitive_text(plan_text)
    if plan_findings:
        raise ArchiveError(
            f"归档计划包含高置信度敏感内容：{plan_findings}"
        )

    connection = open_readonly_db(db_path)
    try:
        sources = load_sessions(connection, plan)
        evidence = load_evidence(connection, plan)
    finally:
        connection.close()

    outputs: dict[str, bytes] = {}
    record_hashes: dict[str, str] = {}
    total_redactions: dict[str, int] = {}
    for record in plan.records:
        document, counts = render_record(record, evidence, sources)
        relative = f"{record.date}/{record.file_name}"
        outputs[relative] = document.encode("utf-8")
        record_hashes[relative] = sha256_text(document)
        merge_counts(total_redactions, counts)

    by_date: dict[str, list[RecordSpec]] = {}
    for record in plan.records:
        by_date.setdefault(record.date, []).append(record)
    for date, records in sorted(by_date.items()):
        daily = render_daily_readme(
            date,
            records,
            record_hashes,
            evidence,
            sources,
        )
        outputs[f"{date}/README.md"] = daily.encode("utf-8")

    outputs["INDEX.md"] = render_index(
        plan,
        record_hashes,
        evidence,
        sources,
    ).encode("utf-8")
    outputs["README.md"] = render_readme(plan).encode("utf-8")
    outputs["SOURCES.sha256"] = render_sources(
        plan_path,
        plan,
        evidence,
        sources,
    ).encode("utf-8")

    for relative, content in outputs.items():
        for finding in find_sensitive_text(content.decode("utf-8")):
            raise ArchiveError(
                f"生成文件 {relative} 仍含高置信度敏感内容：{finding}"
            )

    return BuildResult(
        outputs=outputs,
        evidence=evidence,
        sources=sources,
        record_hashes=record_hashes,
        redaction_counts=total_redactions,
    )


def write_if_changed(path: Path, content: bytes) -> bool:
    if path.is_file() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return True


def verify_outputs(out_dir: Path, result: BuildResult) -> list[str]:
    errors: list[str] = []
    for relative, content in sorted(result.outputs.items()):
        path = out_dir / relative
        if not path.is_file():
            errors.append(f"缺少生成文件：{relative}")
            continue
        actual = path.read_bytes()
        if actual != content:
            errors.append(f"生成文件已过期或被手改：{relative}")
            continue
        findings = find_sensitive_text(actual.decode("utf-8"))
        if findings:
            errors.append(
                f"生成文件 {relative} 含高置信度敏感内容：{findings}"
            )
    return errors


def _print_summary(result: BuildResult) -> None:
    print(
        f"PASS: {len(result.record_hashes)} 篇工程记录，"
        f"{len(result.sources)} 个会话，{len(result.evidence)} 条证据"
    )
    if result.redaction_counts:
        summary = "、".join(
            f"{key}={value}"
            for key, value in sorted(result.redaction_counts.items())
        )
        print(f"脱敏：{summary}")
    else:
        print("脱敏：无高置信度字段命中")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(r"D:\AppData\agentsview\sessions.db"),
        help="AgentsView SQLite database",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("agent-sessions/archive-plan.json"),
        help="archive plan JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("agent-sessions"),
        help="archive output directory",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify output is current and read-only",
    )
    args = parser.parse_args(argv)

    try:
        result = build_archive(args.db, args.plan, args.out)
        if args.check:
            errors = verify_outputs(args.out, result)
            if errors:
                print("FAIL: AI 会话归档校验未通过", file=sys.stderr)
                for error in errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            _print_summary(result)
            print("PASS: 生成文件、源证据和脱敏检查一致")
            return 0

        changed = 0
        for relative, content in sorted(result.outputs.items()):
            if write_if_changed(args.out / relative, content):
                changed += 1
        _print_summary(result)
        print(f"PASS: 写入完成，修改 {changed} 个文件")
        return 0
    except ArchiveError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
