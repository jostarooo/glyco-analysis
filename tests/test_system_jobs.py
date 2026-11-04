from __future__ import annotations

import threading
import time
import unittest

from system.jobs import JobError, JobService
from system.models import PredictionResult, ValidationError


class FakePredictor:
    def __init__(self, *, block: bool = False) -> None:
        self.state = "cold"
        self.started = threading.Event()
        self.release = threading.Event()
        if not block:
            self.release.set()
        self.sequences: list[str] = []

    def predict(self, sequence: str) -> PredictionResult:
        self.state = "ready"
        self.sequences.append(sequence)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test release timeout")
        return PredictionResult(
            sequence_sha256="A" * 64,
            sequence_length=len(sequence),
            candidates=(),
            elapsed_seconds=0.01,
            model={"state": "ready"},
            limitations=("test",),
        )


def wait_until(predicate: object, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


class JobServiceTests(unittest.TestCase):
    def test_job_reaches_success_and_is_owned_by_submitter(self) -> None:
        predictor = FakePredictor()
        service = JobService(predictor)
        try:
            job = service.submit("nst", "demo", protein_id="P1")
            wait_until(lambda: service.get(job.job_id, "demo").status == "succeeded")
            record = service.get(job.job_id, "demo")
            self.assertEqual(record.result.sequence_length, 3)
            self.assertEqual(predictor.sequences, ["NST"])
            with self.assertRaises(JobError) as context:
                service.get(job.job_id, "other")
            self.assertEqual(context.exception.status, 404)
        finally:
            service.close()

    def test_full_queue_returns_429_instead_of_accepting_unbounded_work(self) -> None:
        predictor = FakePredictor(block=True)
        service = JobService(predictor, max_queue=1)
        try:
            first = service.submit("NST", "demo")
            self.assertTrue(predictor.started.wait(timeout=2))
            second = service.submit("NST", "demo")
            with self.assertRaises(JobError) as context:
                service.submit("NST", "demo")
            self.assertEqual(context.exception.status, 429)
            self.assertEqual(second.status, "queued")
            self.assertEqual(first.status, "loading_model")
        finally:
            predictor.release.set()
            service.close()

    def test_invalid_sequence_fails_before_creating_a_job(self) -> None:
        predictor = FakePredictor()
        service = JobService(predictor)
        try:
            with self.assertRaises(ValidationError):
                service.submit("", "demo")
            self.assertEqual(predictor.sequences, [])
        finally:
            service.close()


if __name__ == "__main__":
    unittest.main()
