"""프리셋과 사용자 정의 Max-Cut 입력을 처리하는 Pydantic v2 스키마."""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from classical.common import prepare_adjacency_matrix

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Seed = Annotated[int, Field(strict=True, ge=0)]
Weight = StrictInt | StrictFloat

class InputModel(BaseModel):
    """정의하지 않은 필드와 NaN·무한대 입력을 거절하는 공통 모델."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class QAOAOptions(InputModel):
    """QAOA 회로 깊이, 최대 최적화 횟수, 측정 횟수 및 오류 완화 옵션을 지정한다."""
    p: PositiveInt = 1
    maxiter: PositiveInt = 100
    shots: PositiveInt = 1024
    seed: Seed | None = 42  # 튜닝된 시드값 고정
    mitigation_method: Literal["none", "m3", "zne", "both"] = "both"  # 완화 기법 선택 스위치
    zne_scales: list[int] = Field(default=[1, 3, 5])  # 극한 노이즈 방어용 튜닝 배수

class SDPOptions(InputModel):
    """SDP 무작위 라운딩 횟수와 재현성을 위한 시드를 지정한다."""
    rounds: PositiveInt = 256
    seed: Seed | None = 42  # 프론트엔드와 일치하도록 기본값 변경

class GraphInput(InputModel):
    """인접 행렬과 선택적인 그래프 설명 정보를 입력받는다."""
    matrix: list[list[Weight]]
    num_nodes: Annotated[int, Field(strict=True, ge=2, le=14)] | None = None
    name: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_graph(self):
        n = len(prepare_adjacency_matrix(self.matrix))
        if self.num_nodes is not None and self.num_nodes != n:
            raise ValueError("num_nodes must match the matrix size")
        self.num_nodes = n
        return self

    def to_adjacency_matrix(self) -> list[list[float]]:
        return [row[:] for row in self.matrix]

class MaxCutRequest(GraphInput):
    """그래프와 양자·고전 알고리즘 실행 옵션을 하나의 요청으로 묶는다."""
    qaoa: QAOAOptions = Field(default_factory=QAOAOptions)
    sdp: SDPOptions = Field(default_factory=SDPOptions)

    def to_solver_inputs(self) -> dict:
        """각 함수의 매개변수에 맞춰 키워드 인자를 나누어 반환한다."""
        return {
            "brute_force": {"adjacency": self.to_adjacency_matrix(), "max_nodes": 14},
            "sdp": {"adjacency": self.to_adjacency_matrix(), **self.sdp.model_dump()},
            "qaoa_circuit": {"matrix": self.to_adjacency_matrix(), "p": self.qaoa.p, "measure": False},
            "qaoa_optimizer": {"p": self.qaoa.p, "maxiter": self.qaoa.maxiter},
            "qaoa_sampler": {"shots": self.qaoa.shots, "seed": self.qaoa.seed},
            "mitigation": {
                "method": self.qaoa.mitigation_method,
                "zne_scales": self.qaoa.zne_scales
            }
        }

class AlgorithmResult(InputModel):
    algorithm: Literal["qaoa", "brute_force", "goemans_williamson"]
    assignment: list[Literal[0, 1]]
    partition: list[list[int]]
    bitstring: str
    cut_value: Annotated[float, Field(ge=0)]
    runtime_seconds: Annotated[float, Field(ge=0)]
    details: dict[str, Any] = Field(default_factory=dict)

class AlgorithmError(InputModel):
    code: str
    message: str

class AlgorithmRun(InputModel):
    status: Literal["success", "error"]
    result: AlgorithmResult | None = None
    error: AlgorithmError | None = None

class ApproximationRatio(InputModel):
    value: Annotated[float, Field(ge=0, le=1)] | None = None
    reason: str | None = None

class ComparisonResponse(InputModel):
    status: Literal["success", "partial_success", "error"]
    num_nodes: int
    results: dict[str, AlgorithmRun]
    optimal_cut_value: float | None
    approximation_ratios: dict[str, ApproximationRatio]