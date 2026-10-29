from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


feasibility = load_script(
    "classify_doc2agent_feasibility_test",
    "scripts/classify_doc2agent_feasibility.py",
)


class ClassifyStatusesTest(unittest.TestCase):
    def test_all_ok_is_direct(self) -> None:
        self.assertEqual(feasibility.classify_statuses(["ok", "ok"]), feasibility.DIRECT)

    def test_non_service_wrapper_error_needs_replacement(self) -> None:
        self.assertEqual(
            feasibility.classify_statuses(["ok", "param_error"]),
            feasibility.REPLACEMENT,
        )

    def test_service_failure_takes_precedence(self) -> None:
        self.assertEqual(
            feasibility.classify_statuses(["param_error", "server_error"]),
            feasibility.SERVICE,
        )


class RealInventoryTest(unittest.TestCase):
    def test_50_tasks_have_one_primary_category_and_sum_to_50(self) -> None:
        import csv

        with feasibility.DEFAULT_TASKS.open(newline="", encoding="utf-8") as handle:
            tasks = list(csv.DictReader(handle))
        tools = feasibility.load_tools(feasibility.DEFAULT_TOOLS)
        runs = feasibility.load_runs(feasibility.DEFAULT_RUNS, 50)
        records = feasibility.build_records(
            tasks,
            tools,
            runs,
            feasibility.DEFAULT_RUNS,
        )
        feasibility.validate_records(records, 50)
        counts = {
            category: sum(record["category"] == category for record in records)
            for category in feasibility.CATEGORIES
        }
        self.assertEqual(counts[feasibility.DIRECT], 20)
        self.assertEqual(counts[feasibility.REPLACEMENT], 25)
        self.assertEqual(counts[feasibility.SERVICE], 5)


if __name__ == "__main__":
    unittest.main()
