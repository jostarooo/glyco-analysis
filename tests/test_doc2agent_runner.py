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


runner = load_script("run_doc2agent_qwen3_test", "scripts/run_doc2agent_qwen3.py")


class ParseJsonObjectTest(unittest.TestCase):
    def test_direct_object(self) -> None:
        self.assertEqual(
            runner.parse_json_object('{"action":"finish","answer":"ok"}'),
            {"action": "finish", "answer": "ok"},
        )

    def test_object_embedded_in_text(self) -> None:
        self.assertEqual(
            runner.parse_json_object(
                'decision follows\n{"action":"call_tool","tool":"x","arguments":{}}\n'
            ),
            {"action": "call_tool", "tool": "x", "arguments": {}},
        )

    def test_truncated_object_returns_empty(self) -> None:
        self.assertEqual(
            runner.parse_json_object(
                '{"action":"call_tool","tool":"x","arguments":{"wurcs":"WURCS=2.0/'
            ),
            {},
        )

    def test_non_object_returns_empty(self) -> None:
        self.assertEqual(runner.parse_json_object('["not", "an", "object"]'), {})


if __name__ == "__main__":
    unittest.main()
