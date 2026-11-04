from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import PredictionResult, find_sequons, normalize_sequence
from .predictor import PredictorError


class InferencePort(Protocol):
    @property
    def state(self) -> str: ...

    def predict(self, sequence: str) -> PredictionResult: ...


class JobError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class JobRecord:
    job_id: str
    username: str
    sequence: str
    protein_id: str | None
    status: str = "queued"
    stage: str = "等待推理队列"
    queue_position: int = 0
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: PredictionResult | None = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage,
            "queue_position": self.queue_position,
            "submitted_at": self.submitted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "sequence_length": len(self.sequence),
            "protein_id": self.protein_id,
        }
        if self.result is not None:
            payload["result"] = self.result.to_dict()
        if self.error is not None:
            payload["error"] = dict(self.error)
        return payload


class JobService:
    def __init__(
        self,
        predictor: InferencePort,
        *,
        max_queue: int = 4,
        ttl_seconds: int = 1800,
    ) -> None:
        if max_queue < 1:
            raise ValueError("max_queue must be at least 1")
        self.predictor = predictor
        self.max_queue = max_queue
        self.ttl_seconds = ttl_seconds
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="glyco-inference-worker",
            daemon=True,
        )
        self._worker.start()

    def submit(
        self,
        raw_sequence: object,
        username: str,
        protein_id: str | None = None,
    ) -> JobRecord:
        sequence = normalize_sequence(raw_sequence)
        job = JobRecord(
            job_id=uuid.uuid4().hex,
            username=username,
            sequence=sequence,
            protein_id=protein_id,
            queue_position=self._queue.qsize() + 1,
        )
        with self._lock:
            self._prune_locked()
            self._jobs[job.job_id] = job
        try:
            self._queue.put_nowait(job.job_id)
        except queue.Full as error:
            with self._lock:
                self._jobs.pop(job.job_id, None)
            raise JobError(
                "QUEUE_FULL",
                "推理队列已满，请稍后重试",
                status=429,
            ) from error
        return job

    def get(self, job_id: str, username: str) -> JobRecord:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None or job.username != username:
                raise JobError("JOB_NOT_FOUND", "任务不存在", status=404)
            return job

    def close(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=2.0)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                break
            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = (
                "loading_model"
                if find_sequons(job.sequence) and self.predictor.state == "cold"
                else "running"
            )
            job.stage = (
                "首次加载真实 ESM-2 150M LoRA 检查点"
                if job.status == "loading_model"
                else "计算 N-X-S/T 位点"
            )
            job.queue_position = 0
            job.started_at = datetime.now(timezone.utc)

        try:
            result = self.predictor.predict(job.sequence)
        except PredictorError as error:
            self._finish_error(job_id, error.code, error.message)
        except Exception as error:
            self._finish_error(
                job_id,
                "INFERENCE_FAILED",
                f"推理任务失败：{type(error).__name__}",
            )
        else:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "succeeded"
                job.stage = "完成"
                job.result = result
                job.finished_at = datetime.now(timezone.utc)

    def _finish_error(
        self,
        job_id: str,
        code: str,
        message: str,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.stage = "失败"
            job.error = {"code": code, "message": message}
            job.finished_at = datetime.now(timezone.utc)

    def _prune_locked(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {"succeeded", "failed"}
            and job.finished_at is not None
            and job.finished_at.timestamp() < cutoff
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
