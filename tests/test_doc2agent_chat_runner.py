import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_doc2agent_qwen3 as runner  # noqa: E402


def add(a: int, b: int) -> int:
    return a + b


class FakeChat:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> runner.ChatReply:
        self.messages.append([dict(message) for message in messages])
        if len(self.messages) == 1:
            return runner.ChatReply(
                content='{"action":"call_tool","tool":"add","arguments":{"a":"2","b":"3"}}',
                elapsed_seconds=0.1,
                finish_reason="tool_calls",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        return runner.ChatReply(
            content='{"action":"finish","answer":"5"}',
            elapsed_seconds=0.2,
            finish_reason="stop",
            usage={"prompt_tokens": 20, "completion_tokens": 4, "total_tokens": 24},
        )


class SharedChatRunnerTest(unittest.TestCase):
    def test_fake_chat_drives_real_tool_call_then_finish(self) -> None:
        tools = {
            "add": runner.Tool(
                name="add",
                signature=inspect.signature(add),
                description="Add two integers",
                function=add,
            )
        }
        task = {
            "task_id": 7,
            "question": "What is 2 plus 3?",
            "expected_tools": ["add"],
        }
        chat = FakeChat()

        result = runner.run_task_with_chat(
            task,
            tools,
            max_rounds=4,
            system="test system",
            chat_fn=chat,
            chat_label="fake",
        )

        self.assertEqual(result.final_answer, "5")
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["tool"], "add")
        self.assertEqual(result.tool_calls[0]["arguments"], {"a": "2", "b": "3"})
        self.assertEqual(result.tool_calls[0]["status"], "ok")
        self.assertEqual(result.tool_calls[0]["result"], 5)
        self.assertTrue(result.score()["exact_sequence"])
        self.assertEqual(len(result.model_calls), 2)
        self.assertEqual(
            [call["finish_reason"] for call in result.model_calls],
            ["tool_calls", "stop"],
        )
        self.assertIn("Tool result:", chat.messages[1][-1]["content"])
        self.assertIn('"result": 5', chat.messages[1][-1]["content"])


if __name__ == "__main__":
    unittest.main()
