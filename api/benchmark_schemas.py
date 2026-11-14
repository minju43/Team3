"""Sprint 2 벤치마크와 비동기 Job의 요청·응답 형식."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AliasChoices, Field

from .schemas import AlgorithmError, AlgorithmRun, ApproximationRatio, ComparisonResponse, InputModel, MaxCutRequest, Weight

BackendMode = Literal["ideal", "noisy_sim", "real_qpu"]
JobStatus = Literal["queued", "running", "completed", "failed"]
BenchmarkKey = Literal["brute_force", "sdp", "raw_qaoa", "mitigated_qaoa"]
Probability = Annotated[float, Field(strict=True, ge=0, le=1)]

BENCHMARK_LABELS = {
    "brute_force": "Brute-Force",
    "sdp": "SDP",
    "raw_qaoa": "Raw QAOA",
    "mitigated_qaoa": "Mitigated QAOA",
}


class BenchmarkRequest(MaxCutRequest):
    """프리셋의 matrix와 캔버스의 adjacency_matrix를 모두 받는다."""

    matrix: list[list[Weight]] = Field(validation_alias=AliasChoices("matrix", "adjacency_matrix"))
    backend: BackendMode = "noisy_sim"
    gate_error: Probability = 0.01
    readout_error: Probability = 0.03


class BenchmarkRow(InputModel):
    """대시보드 표와 CSV가 공통으로 사용하는 알고리즘 한 행."""

    key: BenchmarkKey
    algorithm: str
    status: Literal["success", "error"]
    max_cut_value: float | None
    time: float | None
    approximation_ratio: float | None
    approximation_ratio_reason: str | None
    bitstring: str | None
    error_code: str | None
    error_message: str | None


class BenchmarkResponse(ComparisonResponse):
    """비교 상세 결과에 실행 백엔드와 대시보드용 표를 추가한다."""

    backend: BackendMode
    results: dict[BenchmarkKey, AlgorithmRun]
    approximation_ratios: dict[BenchmarkKey, ApproximationRatio]
    benchmarks: list[BenchmarkRow]


class QuantumJob(InputModel):
    """Aer 또는 IBM에 제출된 샘플링 작업의 식별자와 제공자 상태."""

    job_id: str
    backend_name: str
    status: str


class JobResponse(InputModel):
    """한 번의 벤치마크 제출에 대한 상태, 결과, 오류를 제공한다."""

    job_id: UUID
    status: JobStatus
    backend: BackendMode
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    quantum_job: QuantumJob | None = None
    result: BenchmarkResponse | None = None
    error: AlgorithmError | None = None
