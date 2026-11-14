"""벤치마크를 백그라운드에서 실행하고 상태와 결과를 메모리에 저장한다."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from .benchmark import run_benchmark
from .benchmark_schemas import BenchmarkRequest, JobResponse, QuantumJob
from .schemas import AlgorithmError

logger = logging.getLogger(__name__)


class JobQueueFull(RuntimeError):
    """캐시에 진행 중인 작업이 가득 차서 새 요청을 받을 수 없다."""


class JobQueue:
    """동시에 실행할 작업 수를 제한하고, 종료된 결과는 일정 기간 보관한다."""

    def __init__(self, *, workers: int = 2, capacity: int = 128, ttl_seconds: int = 3600):
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="benchmark")
        self._lock = Lock()
        self._jobs: dict[UUID, JobResponse] = {}
        self._expires_at: dict[UUID, float] = {}
        self._capacity = capacity
        self._ttl = ttl_seconds

    def _remove_expired(self):
        """캐시 잠금 안에서 만료된 완료·실패 작업을 삭제한다."""
        now = monotonic()
        for job_id, expiry in list(self._expires_at.items()):
            if expiry <= now:
                del self._expires_at[job_id]
                del self._jobs[job_id]

    def submit(self, request: BenchmarkRequest) -> JobResponse:
        """작업을 등록하고 계산이 끝나기 전에 큐 등록 응답을 반환한다."""
        job = JobResponse(job_id=uuid4(), status="queued", backend=request.backend,
                          created_at=datetime.now(timezone.utc))
        with self._lock:
            self._remove_expired()
            if len(self._jobs) >= self._capacity:
                if not self._expires_at:
                    raise JobQueueFull
                # 활성 작업은 보존하고, 가장 먼저 끝난 결과부터 자리를 비운다.
                oldest = next(iter(self._expires_at))
                del self._expires_at[oldest]
                del self._jobs[oldest]
            self._jobs[job.job_id] = job
            try:
                self._executor.submit(self._run, job.job_id, request)
            except RuntimeError:
                del self._jobs[job.job_id]
                raise
        return job

    def get(self, job_id: UUID) -> JobResponse | None:
        """진행 중인 작업의 최신 상태 또는 저장된 최종 결과를 돌려준다."""
        with self._lock:
            self._remove_expired()
            return self._jobs.get(job_id)

    def _update(self, job_id: UUID, **changes):
        # 응답과 다운로드가 같은 스냅샷을 읽도록 레코드를 통째로 교체한다.
        with self._lock:
            self._jobs[job_id] = self._jobs[job_id].model_copy(update=changes)
            if changes.get("finished_at") is not None:
                self._expires_at[job_id] = monotonic() + self._ttl

    def _run(self, job_id: UUID, request: BenchmarkRequest):
        def report_job(quantum_job: QuantumJob):
            self._update(job_id, quantum_job=quantum_job)

        self._update(job_id, status="running", started_at=datetime.now(timezone.utc))
        try:
            result = run_benchmark(request, report_job)
        except Exception:
            logger.exception("벤치마크 Job 실행 실패: %s", job_id)
            self._update(job_id, status="failed", finished_at=datetime.now(timezone.utc),
                         error=AlgorithmError(code="benchmark_failed", message="벤치마크 작업 실행 중 오류가 발생했습니다."))
        else:
            # 전체 알고리즘이 실패해도 개별 오류 표를 조회하거나 내려받을 수 있다.
            status = "failed" if result.status == "error" else "completed"
            error = (AlgorithmError(code="all_algorithms_failed", message="모든 알고리즘 실행에 실패했습니다.")
                     if status == "failed" else None)
            self._update(job_id, status=status, finished_at=datetime.now(timezone.utc), result=result, error=error)
