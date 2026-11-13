"""기존 코어 검증기와 연동하는 고전 알고리즘의 입력 변환을 검증한다."""
import sys
from pathlib import Path

import numpy as np
import pytest

# 기존 테스트와 같이 프로젝트 모듈을 직접 불러올 수 있도록 경로를 추가한다.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from classical import brute_force_max_cut, goemans_williamson_max_cut
from classical.common import prepare_adjacency_matrix
from core.validator import validate_adjacency_matrix


# pytest와 파일 직접 실행에서 동일한 테스트 입력을 사용한다.
INVALID_MATRICES = [
    [], [[0]], [[0] * 15 for _ in range(15)],
    [[0, 1], [1]], [[0, 1], None], [0, 1],
    [[0, True], [True, 0]], [[0, "1"], ["1", 0]],
    [[0, 1j], [1j, 0]], [[0, float("nan")], [float("nan"), 0]],
    [[0, float("inf")], [float("inf"), 0]], [[0, -1], [-1, 0]],
    [[1, 0], [0, 0]], [[0, 1], [1 + 1e-12, 0]],
    [[0, 1e308, 1e308], [1e308, 0, 1e308], [1e308, 1e308, 0]],
    [[0, 10**1000], [10**1000, 0]],
]

VALID_MATRICES = [
    [[0, 5], [5, 0]], ((0, 5), (5, 0)), np.array([[0, 5], [5, 0]]),
]

SOLVERS = [brute_force_max_cut, goemans_williamson_max_cut]


@pytest.mark.parametrize("matrix", INVALID_MATRICES)
def test_preparation_reports_invalid_inputs_as_value_error(matrix):
    """기존 코어 예외와 변환 오류가 호출부에 ValueError로 전달되는지 확인한다."""
    with pytest.raises(ValueError):
        prepare_adjacency_matrix(matrix)


@pytest.mark.parametrize("matrix", VALID_MATRICES)
def test_conversion_preserves_input_and_returns_float_copy(matrix):
    """검증기는 노드 수를 반환하고 변환기는 원본과 독립된 계산 배열을 만든다."""
    assert validate_adjacency_matrix(np.asarray(matrix).tolist()) == 2
    weights = prepare_adjacency_matrix(matrix)
    assert weights.dtype == np.float64
    weights[0, 1] = 99
    assert matrix[0][1] == 5


@pytest.mark.parametrize("solver", SOLVERS)
def test_solvers_share_core_node_limit(solver):
    """직접 호출하는 두 고전 알고리즘도 코어와 같은 노드 수 기준을 적용한다."""
    with pytest.raises(ValueError):
        solver(np.zeros((15, 15)))


if __name__ == "__main__":
    print("=== 고전 알고리즘 입력 변환 검증 시작 ===")
    # 잘못된 입력, 정상 변환, 노드 제한을 기존 테스트 함수로 각각 확인한다.
    cases = [(f"잘못된 입력 거절 {i}", test_preparation_reports_invalid_inputs_as_value_error, (matrix,))
             for i, matrix in enumerate(INVALID_MATRICES, 1)]
    cases += [(f"원본 유지 및 실수 배열 변환 {i}", test_conversion_preserves_input_and_returns_float_copy, (matrix,))
              for i, matrix in enumerate(VALID_MATRICES, 1)]
    cases += [(f"{solver.__name__} 노드 수 제한", test_solvers_share_core_node_limit, (solver,))
              for solver in SOLVERS]
    passed = failed = 0
    for label, test, args in cases:
        try:
            test(*args)
        except (Exception, pytest.fail.Exception) as exc:
            failed += 1
            print(f"[실패] {label}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[성공] {label}")
    print(f"\n입력 변환 결과: 성공 {passed}개 / 실패 {failed}개")
    raise SystemExit(1 if failed else 0)
