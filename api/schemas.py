"""프리셋과 사용자 정의 Max-Cut 입력을 처리하는 Pydantic v2 스키마.

그래프 검증과 노드 수 제한은 기존 core.validator의 기준을 사용한다.
HTTP 요청을 검증할 때 Qiskit을 불러올 필요는 없다.
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from classical.common import prepare_adjacency_matrix

# 공통 자료형: 실행 횟수와 시드는 엄격한 정수형으로, 가중치는 실수형 숫자로 제한한다.
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Seed = Annotated[int, Field(strict=True, ge=0)]
Weight = StrictInt | StrictFloat


class InputModel(BaseModel):
    """정의하지 않은 필드와 NaN·무한대 입력을 거절하는 공통 모델."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class QAOAOptions(InputModel):
    """QAOA 회로 깊이, 최대 최적화 횟수, 측정 횟수를 지정한다."""
    p: PositiveInt = 1
    maxiter: PositiveInt = 100
    shots: PositiveInt = 1024


class SDPOptions(InputModel):
    """SDP 무작위 라운딩 횟수와 재현성을 위한 시드를 지정한다."""
    rounds: PositiveInt = 256
    seed: Seed | None = 0


class GraphInput(InputModel):
    """인접 행렬과 선택적인 그래프 설명 정보를 입력받는다."""
    matrix: list[list[Weight]]
    num_nodes: Annotated[int, Field(strict=True, ge=2, le=14)] | None = None
    name: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_graph(self):
        """코어 연동과 수치 변환을 확인하고 요청에 명시된 노드 수를 검사한다."""
        # 코어의 원래 예외를 ValueError로 연결하여 Pydantic 검증 오류로 처리한다.
        n = len(prepare_adjacency_matrix(self.matrix))
        if self.num_nodes is not None and self.num_nodes != n:
            raise ValueError("num_nodes must match the matrix size")
        self.num_nodes = n
        return self

    def to_adjacency_matrix(self) -> list[list[float]]:
        """알고리즘 실행 중 원본이 바뀌지 않도록 행렬의 독립된 복사본을 반환한다."""
        return [row[:] for row in self.matrix]


class MaxCutRequest(GraphInput):
    """그래프와 양자·고전 알고리즘 실행 옵션을 하나의 요청으로 묶는다."""
    qaoa: QAOAOptions = Field(default_factory=QAOAOptions)
    sdp: SDPOptions = Field(default_factory=SDPOptions)

    def to_solver_inputs(self) -> dict:
        """각 함수의 매개변수에 맞춰 키워드 인자를 나누어 반환한다.

        QAOA 단계별로 함수의 입력 형식이 다르므로 필요한 인자만 전달한다.
        get_best_partition 호출 시 회로와 최적 각도는 별도로 전달해야 한다.
        기존 코어 샘플러는 시드나 인접 행렬을 입력받지 않는다.
        """
        return {
            "brute_force": {"adjacency": self.to_adjacency_matrix(), "max_nodes": 14},
            "sdp": {"adjacency": self.to_adjacency_matrix(), **self.sdp.model_dump()},
            "qaoa_circuit": {"matrix": self.to_adjacency_matrix(), "p": self.qaoa.p, "measure": False},
            "qaoa_optimizer": {"p": self.qaoa.p, "maxiter": self.qaoa.maxiter},
            "qaoa_sampler": {"shots": self.qaoa.shots},
        }


# 출력 스키마: 알고리즘의 원래 반환 자료형을 API 공통 응답으로 통일한다.
class AlgorithmResult(InputModel):
    """노드 순서의 분할, 실제 컷 값, 전체 실행 시간과 부가 정보를 담는다."""
    algorithm: Literal["qaoa", "brute_force", "goemans_williamson"]
    assignment: list[Literal[0, 1]]
    partition: list[list[int]]
    bitstring: str
    cut_value: Annotated[float, Field(ge=0)]
    runtime_seconds: Annotated[float, Field(ge=0)]
    details: dict[str, Any] = Field(default_factory=dict)


class AlgorithmError(InputModel):
    """다른 알고리즘의 결과와 별개로 보고할 실행 실패 정보."""
    code: str
    message: str


class AlgorithmRun(InputModel):
    """한 알고리즘의 실행 성공 여부와 결과 또는 오류를 담는다."""
    status: Literal["success", "error"]
    result: AlgorithmResult | None = None
    error: AlgorithmError | None = None


class ApproximationRatio(InputModel):
    """실제 컷 값 / BF 최적값과, 계산할 수 없는 경우의 사유를 담는다."""
    value: Annotated[float, Field(ge=0, le=1)] | None = None
    reason: str | None = None


class ComparisonResponse(InputModel):
    """세 알고리즘의 독립 실행 결과와 BF 기준 근사비 분석을 반환한다."""
    status: Literal["success", "partial_success", "error"]
    num_nodes: int
    results: dict[str, AlgorithmRun]
    optimal_cut_value: float | None
    approximation_ratios: dict[str, ApproximationRatio]
