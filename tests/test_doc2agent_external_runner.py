from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_doc2agent_external as external  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        *,
        ok: bool,
        status_code: int = 200,
        payload: Any = None,
        text: str = "",
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ExternalRunnerTest(unittest.TestCase):
    def test_http_payload_and_choices_parsing(self) -> None:
        secret = "test-secret-value"
        config = external.OpenAIConfig(api_key_env="TEST_MAGPIE_KEY")
        messages = [{"role": "user", "content": "Return JSON"}]
        response = FakeResponse(
            ok=True,
            payload={
                "choices": [
                    {
                        "message": {"content": '{"action":"finish","answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                    "total_tokens": 19,
                },
            },
        )

        with patch.dict(os.environ, {"TEST_MAGPIE_KEY": secret}, clear=True):
            with patch.object(external.requests, "post", return_value=response) as post:
                reply = external.call_openai_compatible(messages, config)

        self.assertEqual(reply.content, '{"action":"finish","answer":"ok"}')
        self.assertEqual(reply.finish_reason, "stop")
        self.assertEqual(reply.usage["total_tokens"], 19)
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, external.DEFAULT_ENDPOINT)
        self.assertEqual(kwargs["json"]["model"], external.DEFAULT_MODEL)
        self.assertEqual(kwargs["json"]["messages"], messages)
        self.assertEqual(kwargs["json"]["temperature"], 0.0)
        self.assertEqual(kwargs["json"]["max_tokens"], 512)
        self.assertFalse(kwargs["json"]["stream"])
        self.assertNotIn("tools", kwargs["json"])
        self.assertNotIn("tool_choice", kwargs["json"])
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {secret}")

    def test_non_2xx_is_reported_without_leaking_api_key(self) -> None:
        secret = "test-secret-value"
        config = external.OpenAIConfig(api_key_env="TEST_MAGPIE_KEY")
        response = FakeResponse(
            ok=False,
            status_code=429,
            text=f"rate limited for {secret}",
        )

        with patch.dict(os.environ, {"TEST_MAGPIE_KEY": secret}, clear=True):
            with patch.object(external.requests, "post", return_value=response):
                with self.assertRaises(external.ExternalChatError) as raised:
                    external.call_openai_compatible(
                        [{"role": "user", "content": "hello"}], config
                    )

        message = str(raised.exception)
        self.assertIn("status=429", message)
        self.assertIn("<redacted>", message)
        self.assertNotIn(secret, message)

    def test_network_failure_is_wrapped_without_leaking_api_key(self) -> None:
        secret = "test-secret-value"
        config = external.OpenAIConfig(api_key_env="TEST_MAGPIE_KEY")

        with patch.dict(os.environ, {"TEST_MAGPIE_KEY": secret}, clear=True):
            with patch.object(
                external.requests,
                "post",
                side_effect=external.requests.ConnectionError(f"down {secret}"),
            ):
                with self.assertRaises(external.ExternalChatError) as raised:
                    external.call_openai_compatible(
                        [{"role": "user", "content": "hello"}], config
                    )

        message = str(raised.exception)
        self.assertIn("network_error", message)
        self.assertIn("<redacted>", message)
        self.assertNotIn(secret, message)

    def test_malformed_choice_content_is_rejected(self) -> None:
        config = external.OpenAIConfig(api_key_env="TEST_MAGPIE_KEY")
        response = FakeResponse(
            ok=True,
            payload={
                "choices": [
                    {
                        "message": {"content": None},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        with patch.object(external.requests, "post", return_value=response):
            with self.assertRaises(external.ExternalChatError) as raised:
                external.call_openai_compatible(
                    [{"role": "user", "content": "hello"}], config
                )

        self.assertIn("message.content is not a string", str(raised.exception))
        self.assertEqual(external.METRICS_SCOPE, "trajectory_only")
        self.assertEqual(external.ANSWER_CORRECTNESS, "not_evaluated")
        self.assertEqual(
            external.GRADER, "not_run_upstream_requires_gpt4o_api_key"
        )

    def test_run_payload_records_finish_reason_usage_and_model_calls(self) -> None:
        run = SimpleNamespace(
            task_id=1,
            question="Question",
            expected_tools=["tool"],
            tool_calls=[],
            final_answer="",
            errors=[],
            elapsed_seconds=1.25,
            model_calls=[
                {
                    "round": 1,
                    "elapsed_seconds": 1.0,
                    "finish_reason": "length",
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 512,
                        "total_tokens": 612,
                    },
                }
            ],
            score=lambda: {
                "exact_sequence": False,
                "all_expected_called": False,
                "any_expected_called": False,
                "expected_steps": 1,
                "called_steps": 0,
                "call_successes": 0,
            },
        )

        payload = external.run_payload(run)

        self.assertEqual(payload["model_calls"], 1)
        self.assertEqual(payload["finish_reasons"], {"length": 1})
        self.assertEqual(payload["token_usage"]["total_tokens"], 612)
        self.assertEqual(
            payload["model_responses"][0]["finish_reason"], "length"
        )
        for key in ("accuracy", "correctness", "answer_accuracy"):
            self.assertNotIn(key, payload)


if __name__ == "__main__":
    unittest.main()
