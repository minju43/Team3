"""고전·양자 알고리즘의 서로 다른 출력을 API 응답 형식으로 변환한다."""
from math import isfinite
from numbers import Real

from classical.common import CutResult, cut_value, prepare_adjacency_matrix

from .errors import AlgorithmExecutionError
from .schemas import AlgorithmResult


def _partition_result(adjacency, *, algorithm, assignment, runtime_seconds, details=None):
    """노드별 이진 배정과 실행 시간을 검증하고 실제 컷 값을 계산한다."""
    # 원래 솔버의 보고 값과 독립적으로 분할의 유효성을 확인한다.
    weights = prepare_adjacency_matrix(adjacency)
    bits = list(assignment)
    if len(bits) != len(weights) or any(bit not in (0, 1) for bit in bits):
        raise AlgorithmExecutionError("노드마다 하나의 이진 그룹 배정이 필요합니다.")
    if (isinstance(runtime_seconds, bool) or not isinstance(runtime_seconds, Real)
            or not isfinite(runtime_seconds) or runtime_seconds < 0):
        raise AlgorithmExecutionError("실행 시간은 유한한 비음수여야 합니다.")
    return AlgorithmResult(
        algorithm=algorithm, assignment=bits,
        partition=[[i for i, bit in enumerate(bits) if bit == group] for group in (0, 1)],
        bitstring="".join(map(str, bits)), cut_value=cut_value(weights, bits),
        runtime_seconds=float(runtime_seconds), details=details or {},
    )


def classical_result_to_api(adjacency, result: CutResult) -> AlgorithmResult:
    """고전 계산 결과를 검증하고 솔버별 추가 정보를 details로 분리한다."""
    data = result.to_dict()
    common_fields = {"algorithm", "assignment", "partition", "bitstring", "cut_value", "runtime_seconds"}
    mapped = _partition_result(
        adjacency, algorithm=result.algorithm, assignment=result.assignment,
        runtime_seconds=result.runtime_seconds,
        details={key: value for key, value in data.items() if key not in common_fields},
    )
    if not isfinite(result.cut_value) or result.cut_value != mapped.cut_value:
        raise AlgorithmExecutionError("솔버의 컷 값이 실제 분할에서 계산한 컷 값과 다릅니다.")
    return mapped


def sampled_partition_result(adjacency, sample: tuple, *, runtime_seconds: float,
                             details: dict | None = None) -> AlgorithmResult:
    """QAOA 샘플러의 네 반환값을 API 결과로 변환한다.

    코어에서 이미 뒤집은 비트 순서를 유지하고 실제 컷 값은 분할에서 계산한다.
    최적화 에너지는 상수 오프셋이 빠져 있으므로 실제 컷 값으로 사용하지 않는다.
    """
    # 코어 샘플러의 반환 구조와 비트스트링을 검사한다.
    if len(sample) != 4:
        raise AlgorithmExecutionError("샘플러는 비트스트링, 두 그룹, 준확률 분포를 반환해야 합니다.")
    bits, group_a, group_b, _ = sample
    if not isinstance(bits, str) or set(bits) - {"0", "1"}:
        raise AlgorithmExecutionError("샘플러 비트스트링은 0과 1로 구성되어야 합니다.")
    result = _partition_result(
        adjacency, algorithm="qaoa", assignment=list(map(int, bits)),
        runtime_seconds=runtime_seconds, details=details,
    )
    # 노드 순서가 잘못 뒤집히거나 그룹 정보와 불일치하는 출력을 거절한다.
    if [list(group_a), list(group_b)] != result.partition:
        raise AlgorithmExecutionError("샘플러의 그룹과 비트스트링이 일치하지 않습니다.")
    return result
