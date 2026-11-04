from __future__ import annotations

import http.client
import json
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any

from system.auth import AuthService
from system.http_app import AppContext, make_server
from system.jobs import JobService
from system.models import PredictionResult
from system.samples import SampleProvider


REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntime:
    state = "ready"
    state_message = ""

    def predict(self, sequence: str) -> PredictionResult:
        return PredictionResult(
            sequence_sha256="B" * 64,
            sequence_length=len(sequence),
            candidates=(),
            elapsed_seconds=0.01,
            model=self.model_info(),
            limitations=("test only",),
        )

    def model_info(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "state_message": self.state_message,
            "device": "test",
            "adapter_sha256": "C" * 64,
        }


class HTTPContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.jobs = JobService(self.runtime)
        self.context = AppContext(
            head="D" * 40,
            auth=AuthService.with_password(
                "demo",
                "secret",
                session_ttl=timedelta(hours=1),
            ),
            jobs=self.jobs,
            predictor=self.runtime,
            samples=SampleProvider(REPO_ROOT),
            index_html=b"<!doctype html><title>test</title>",
        )
        self.server = make_server(self.context, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        self.cookie = ""
        self.csrf = ""

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.jobs.close()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        csrf: bool = False,
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        headers: dict[str, str] = {}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        parsed = json.loads(raw) if raw else {}
        return response.status, parsed, response_headers

    def login(self) -> None:
        status, payload, headers = self.request(
            "POST",
            "/api/auth/login",
            {"username": "demo", "password": "secret"},
        )
        self.assertEqual(status, 200)
        self.cookie = headers["set-cookie"].split(";", 1)[0]
        self.csrf = payload["csrf_token"]

    def test_unauthenticated_prediction_request_is_rejected(self) -> None:
        status, payload, _ = self.request(
            "POST",
            "/api/predictions",
            {"sequence": "NST"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "AUTH_REQUIRED")

    def test_login_submit_poll_and_unknown_job(self) -> None:
        self.login()
        status, submitted, _ = self.request(
            "POST",
            "/api/predictions",
            {"sequence": "NST", "protein_id": "P1"},
            csrf=True,
        )
        self.assertEqual(status, 202)
        job_id = submitted["job_id"]
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status, job, _ = self.request("GET", f"/api/predictions/{job_id}")
            if job["status"] == "succeeded":
                break
            time.sleep(0.01)
        self.assertEqual(status, 200)
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["protein_id"], "P1")

        status, missing, _ = self.request("GET", "/api/predictions/" + "0" * 32)
        self.assertEqual(status, 404)
        self.assertEqual(missing["error"]["code"], "JOB_NOT_FOUND")

    def test_csrf_is_required_for_state_changes(self) -> None:
        self.login()
        status, payload, _ = self.request(
            "POST",
            "/api/predictions",
            {"sequence": "NST"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "CSRF_REJECTED")

    def test_runtime_reports_head_and_model_provenance(self) -> None:
        self.login()
        status, payload, _ = self.request("GET", "/api/runtime")
        self.assertEqual(status, 200)
        self.assertEqual(payload["head"], "D" * 40)
        self.assertEqual(payload["model"]["adapter_sha256"], "C" * 64)


if __name__ == "__main__":
    unittest.main()
