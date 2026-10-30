from __future__ import annotations

import csv
import importlib.util
import sys
import unittest
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recheck = load_script(
    "retest_doc2agent_blockers_test",
    "scripts/retest_doc2agent_blockers.py",
)


class FakeResponse:
    def __init__(self, status_code: int, payload: Any, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        return self._payload


def make_spec(task_fit: str = "direct") -> Any:
    return recheck.ProbeSpec(
        tool="example",
        source_tasks=(1,),
        w2_classes=("bad_request",),
        args={},
        probe_basis="test",
        expected_kind="json_2xx",
        task_fit=task_fit,
        task_impact="test",
    )


def make_observation(
    status: int | None = 200,
    error: str = "",
    content_satisfied: bool = True,
) -> Any:
    return recheck.ProbeObservation(
        tool="example",
        probe_kind="task_required",
        args={},
        http_status=status,
        elapsed_ms=1,
        attempts_used=1,
        request_url="https://example.test",
        return_type="Response",
        response_summary="test",
        error=error,
        content_satisfied=content_satisfied,
        content_note="test",
    )


class ClassifierTest(unittest.TestCase):
    def test_http_400_is_api_contract_failure(self) -> None:
        result = recheck.classify_observation(
            make_spec(),
            make_observation(status=400, content_satisfied=False),
            None,
        )
        self.assertEqual(result, recheck.API)

    def test_http_200_with_missing_content_is_api_contract_failure(self) -> None:
        result = recheck.classify_observation(
            make_spec(),
            make_observation(status=200, content_satisfied=False),
            None,
        )
        self.assertEqual(result, recheck.API)

    def test_certificate_verification_is_tls_failure(self) -> None:
        result = recheck.classify_observation(
            make_spec(),
            make_observation(
                status=None,
                error="SSLError: certificate verify failed: unable to get local issuer",
                content_satisfied=False,
            ),
            None,
        )
        self.assertEqual(result, recheck.TLS)

    def test_timeout_is_service_failure(self) -> None:
        result = recheck.classify_observation(
            make_spec(),
            make_observation(
                status=None,
                error="ReadTimeout: request timed out",
                content_satisfied=False,
            ),
            None,
        )
        self.assertEqual(result, recheck.SERVICE)

    def test_missing_dependency_is_not_service_failure(self) -> None:
        result = recheck.classify_observation(
            make_spec(),
            make_observation(
                status=None,
                error="ModuleNotFoundError: No module named 'pandas'",
                content_satisfied=False,
            ),
            None,
        )
        self.assertEqual(result, recheck.DEPENDENCY)

    def test_passing_control_marks_task_redesign(self) -> None:
        spec = make_spec(task_fit="requires_redesign")
        control = make_observation(status=200, content_satisfied=True)
        result = recheck.classify_observation(
            spec,
            make_observation(status=400, content_satisfied=False),
            control,
        )
        self.assertEqual(result, recheck.REDESIGN)


class ContentValidatorTest(unittest.TestCase):
    def test_empty_iupac_object_is_not_a_conversion(self) -> None:
        response = FakeResponse(200, {})
        satisfied, _ = recheck.content_satisfied("iupac_result", response, {})
        self.assertFalse(satisfied)

    def test_iupac_wurcs_object_passes(self) -> None:
        payload = {"wurcs": "WURCS=2.0/1,1,0/[a2122h-1b_1-5]/1/"}
        response = FakeResponse(200, payload)
        satisfied, _ = recheck.content_satisfied("iupac_result", response, payload)
        self.assertTrue(satisfied)

    def test_composition_without_accession_fails_task_gate(self) -> None:
        payload = [{"message": "Accession not found.", "wurcs": "WURCS=2.0/example"}]
        response = FakeResponse(200, payload)
        satisfied, _ = recheck.content_satisfied(
            "wurcs_with_accession",
            response,
            payload,
        )
        self.assertFalse(satisfied)

    def test_composition_with_accession_passes_task_gate(self) -> None:
        payload = [{"id": "G14669DU", "wurcs": "WURCS=2.0/example"}]
        response = FakeResponse(200, payload)
        satisfied, _ = recheck.content_satisfied(
            "wurcs_with_accession",
            response,
            payload,
        )
        self.assertTrue(satisfied)

    def test_empty_structured_result_is_reachable(self) -> None:
        payload: list[dict[str, str]] = []
        response = FakeResponse(200, payload)
        satisfied, note = recheck.content_satisfied(
            "structured_response",
            response,
            payload,
        )
        self.assertTrue(satisfied)
        self.assertIn("length=0", note)

    def test_svg_response_is_image_markup(self) -> None:
        response = FakeResponse(200, None, text='<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        satisfied, _ = recheck.content_satisfied("image_html", response, None)
        self.assertTrue(satisfied)


class RegistryTest(unittest.TestCase):
    def test_registry_covers_every_w2_blocked_tool(self) -> None:
        blocked: set[str] = set()
        with recheck.DEFAULT_W2_CSV.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                blocked.update(
                    value.strip()
                    for value in row["blocking_tools"].split("|")
                    if value.strip()
                )
        registered = {spec.tool for spec in recheck.SPECS}
        self.assertEqual(len(recheck.SPECS), 17)
        self.assertEqual(registered, blocked)

    def test_task_reclassification_corrects_all_resolved_blockers(self) -> None:
        classes = {spec.tool: recheck.PASS for spec in recheck.SPECS}
        classes.update(
            {
                "find": recheck.REDESIGN,
                "get_lectins": recheck.API,
                "convert_composition_text_to_wurcs_format": recheck.API,
                "get_proteins": recheck.TLS,
            }
        )
        revisions, corrections = recheck.build_task_revisions(
            recheck.DEFAULT_W2_CSV,
            [
                recheck.ToolRecord(
                    spec=spec,
                    observation=make_observation(),
                    control=None,
                    recheck_class=classes[spec.tool],
                    service_reachable=True,
                    default_transport_ok=True,
                    root_cause="test",
                    wrapper_file="test",
                    wrapper_sha256="test",
                )
                for spec in recheck.SPECS
            ],
        )
        by_task = {int(row["task_id"]): row for row in revisions}
        changed = {int(row["task_id"]): row for row in corrections}

        self.assertEqual(len(revisions), 50)
        self.assertEqual(len(corrections), 24)
        self.assertEqual(
            by_task[31]["revised_category"],
            recheck.DIRECT,
        )
        self.assertEqual(
            by_task[21]["revised_category"],
            recheck.REPLACEMENT,
        )
        self.assertEqual(
            by_task[37]["revised_category"],
            recheck.DIRECT,
        )
        self.assertEqual(by_task[1]["revised_category"], recheck.DIRECT)
        self.assertEqual(by_task[3]["revised_category"], recheck.DIRECT)
        self.assertEqual(by_task[32]["revised_category"], recheck.DIRECT)
        self.assertEqual(by_task[48]["revised_category"], recheck.REPLACEMENT)
        self.assertEqual(by_task[20]["revised_category"], recheck.W2_SERVICE)
        self.assertEqual(by_task[46]["revised_category"], recheck.W2_SERVICE)

        counts = Counter(row["revised_category"] for row in revisions)
        self.assertEqual(counts[recheck.DIRECT], 43)
        self.assertEqual(counts[recheck.REPLACEMENT], 5)
        self.assertEqual(counts[recheck.W2_SERVICE], 2)
        self.assertEqual(sum(counts.values()), 50)
        self.assertEqual(set(changed), {
            int(row["task_id"])
            for row in revisions
            if row["original_category"] != row["revised_category"]
        })


if __name__ == "__main__":
    unittest.main()
