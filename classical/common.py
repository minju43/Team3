"""고전 알고리즘의 계산용 행렬 변환, 컷 값 계산, 결과 직렬화 기능을 제공한다."""

from dataclasses import asdict, dataclass
from numbers import Integral
from typing import Any, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from core.validator import GraphValidationError, validate_adjacency_matrix as _validate_graph


def positive_integer(value: int, name: str) -> int:
    """불리언을 제외한 양의 정수인지 검사하고 파이썬 정수로 반환한다."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def prepare_adjacency_matrix(adjacency: ArrayLike) -> NDArray[np.float64]:
    """공통 코어 검증기를 호출한 뒤 계산용 float64 행렬의 독립된 복사본을 만든다.

    노드 수·자기 루프·대칭성·음수 가중치 검사는 기존 core.validator에 위임한다.
    코어를 수정하지 않고 입력 형식과 예외를 연결하며, 계산에 필요한 수치 조건을 보완한다.
    """
    # 기존 코어는 리스트를 받으므로 배열·튜플 입력을 숫자 타입 변환 없이 맞춘다.
    if isinstance(adjacency, np.ndarray):
        matrix = adjacency.tolist()
    elif isinstance(adjacency, tuple):
        matrix = [list(row) if isinstance(row, tuple) else row for row in adjacency]
    else:
        matrix = adjacency
    try:
        _validate_graph(matrix)
    except (GraphValidationError, TypeError, IndexError, ValueError) as exc:
        # 코어의 예외 클래스와 잘못된 행 구조에서 발생하는 오류를 호출부에 연결한다.
        raise ValueError("인접 행렬을 검증하지 못했습니다.") from exc

    # float64 변환 시 불리언을 숫자로 오인하거나 무한대·오버플로가 유입되는 것을 막는다.
    if any(isinstance(value, (bool, np.bool_)) for row in matrix for value in row):
        raise ValueError("가중치에 불리언을 사용할 수 없습니다.")
    try:
        weights = np.array(matrix, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("가중치를 계산용 실수 배열로 변환할 수 없습니다.") from exc
    if not np.isfinite(weights).all():
        raise ValueError("계산용 가중치는 유한해야 합니다.")
    with np.errstate(over="ignore"):
        total_weight = np.triu(weights, k=1).sum()
    if not np.isfinite(total_weight):
        raise ValueError("전체 간선 가중치의 합이 실수 표현 범위를 초과합니다.")
    return weights


def _edge_arrays(weights: NDArray[np.float64]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """무방향 간선을 중복 계산하지 않도록 상삼각 부분의 간선만 추출한다."""
    rows, cols = np.nonzero(np.triu(weights, k=1))
    return rows, cols, weights[rows, cols]


def cut_value(adjacency: ArrayLike, assignment: Sequence[int]) -> float:
    """그룹 0과 그룹 1 사이를 연결하는 각 간선의 가중치 w[i,j]를 한 번씩 합산한다."""
    weights = prepare_adjacency_matrix(adjacency)
    bits = np.asarray(assignment)
    if bits.shape != (len(weights),) or not np.isin(bits, [0, 1]).all():
        raise ValueError("assignment must contain one binary value per node")
    rows, cols, edge_weights = _edge_arrays(weights)
    return float(edge_weights[bits[rows] != bits[cols]].sum())


@dataclass(frozen=True)
class CutResult:
    """노드 번호 순서로 그룹을 저장하며, assignment[i]는 i번 노드가 속한 그룹이다."""

    algorithm: str
    assignment: tuple[int, ...]
    cut_value: float
    runtime_seconds: float

    @property
    def partition(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """노드 배정을 그룹 0과 그룹 1의 노드 번호 목록으로 나눈다."""
        return (
            tuple(i for i, bit in enumerate(self.assignment) if bit == 0),
            tuple(i for i, bit in enumerate(self.assignment) if bit == 1),
        )

    @property
    def bitstring(self) -> str:
        """0번 노드부터 순서대로 그룹 번호를 이어 붙인다."""
        return "".join(map(str, self.assignment))

    def to_dict(self) -> dict[str, Any]:
        """향후 API 및 프런트엔드 연동을 위해 JSON으로 변환할 수 있는 데이터를 반환한다."""
        result = asdict(self)
        result["assignment"] = list(self.assignment)
        result["partition"] = [list(group) for group in self.partition]
        result["bitstring"] = self.bitstring
        return result
