"""Sprint 2 벤치마크와 비동기 Job의 요청·응답 형식."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AliasChoices, Field, model_validator

from .schemas import AlgorithmError, AlgorithmRun, ApproximationRatio, ComparisonResponse, GraphMatrix, InputModel, MaxCutRequest

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

    matrix: GraphMatrix = Field(validation_alias=AliasChoices("matrix", "adjacency_matrix"))
    backend: BackendMode = "noisy_sim"
    gate_error: Probability = 0.01
    readout_error: Probability = 0.03
    qpu_backend_name: str | None = Field(default=None, min_length=1)
    qpu_auth: Literal["server", "personal"] | None = None

    @model_validator(mode="after")
    def validate_qpu_options(self):
        if self.qpu_backend_name is not None and self.backend != "real_qpu":
            raise ValueError("qpu_backend_name requires backend=real_qpu")
        if self.qpu_auth is not None and self.backend != "real_qpu":
            raise ValueError("qpu_auth requires backend=real_qpu")
        return self


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


class QEMSample(InputModel):
    """폴딩 배율 하나의 실제 장비 측정과 후처리 결과."""

    scale: int
    shots: int
    depth: int
    two_qubit_gates: int
    measurement_mapping: dict[int, int]
    counts: dict[str, int]
    raw_expected_cut: float
    m3_expected_cut: float | None = None


class QEMReport(InputModel):
    """대표 분할의 Cut과 별도로 계산한 오류 완화 기댓값."""

    raw_expected_cut: float | None = None
    m3_expected_cut: float | None = None
    zne_expected_cut: float | None = None
    m3_zne_expected_cut: float | None = None
    ideal_expected_cut: float | None = None
    extrapolator: Literal["linear"] | None = None
    provider_job_id: str | None = None
    backend_name: str | None = None
    samples: list[QEMSample] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


class BenchmarkResponse(ComparisonResponse):
    """비교 상세 결과에 실행 백엔드와 대시보드용 표를 추가한다."""

    backend: BackendMode
    results: dict[BenchmarkKey, AlgorithmRun]
    approximation_ratios: dict[BenchmarkKey, ApproximationRatio]
    benchmarks: list[BenchmarkRow]
    request: BenchmarkRequest | None = None
    graph_id: str | None = None
    job_id: UUID | None = None
    finished_at: datetime | None = None
    qem: QEMReport | None = None


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
