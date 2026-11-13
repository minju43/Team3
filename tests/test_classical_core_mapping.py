"""양자 코어와 고전 알고리즘의 컷 값, 노드 순서, 입출력 호환성을 검증한다."""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from qiskit.quantum_info import Statevector

# 기존 테스트와 같이 프로젝트 모듈을 직접 불러올 수 있도록 경로를 추가한다.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.schemas import MaxCutRequest
from classical import brute_force_max_cut, cut_value, goemans_williamson_max_cut
from api.mapping import sampled_partition_result
from api.errors import AlgorithmExecutionError
from core.hamiltonian import build_maxcut_pauli_list
from core.qaoa_circuit import build_qaoa_circuit
from core.optimizer import optimize_qaoa_parameters
from core.sampler import get_best_partition


# 노드 순서에 따른 차이를 구분할 수 있도록 서로 다른 간선 가중치를 사용한다.
MATRIX = [[0, 2, 0, 1], [2, 0, 3, 0], [0, 3, 0, 4], [1, 0, 4, 0]]


# pytest와 파일 직접 실행에서 동일한 테스트 입력을 사용한다.
INVALID_MATRICES = [
    [[0, True], [True, 0]], [[0, "2"], ["2", 0]],
    [[0, np.nan], [np.nan, 0]], [[0, np.inf], [np.inf, 0]],
    [[0, 2], [2]], [[0, -1], [-1, 0]],
]

SOLVERS = [brute_force_max_cut, goemans_williamson_max_cut]


def test_all_basis_energies_equal_classical_cut_with_offset():
    """모든 계산 기저에서 해밀토니안 기댓값과 오프셋의 합이 컷 값과 같은지 확인한다."""
    operator, offset = build_maxcut_pauli_list(MATRIX)
    for bits in itertools.product((0, 1), repeat=4):
        state = Statevector.from_int(sum(bit << node for node, bit in enumerate(bits)), 16)
        assert state.expectation_value(operator).real + offset == pytest.approx(cut_value(MATRIX, bits))


def test_node_order_mapping_without_double_reversal():
    """비대칭 비트스트링을 사용해 변환 과정에서 노드 순서가 뒤집히지 않는지 확인한다."""
    sample = ("1000", [1, 2, 3], [0], {1: 1.0})
    result = sampled_partition_result(MATRIX, sample, runtime_seconds=0.1)
    assert result.assignment == [1, 0, 0, 0]
    assert result.cut_value == 3
    assert (result.bitstring, *result.partition) == sample[:3]
    assert json.loads(json.dumps(result.model_dump()))["bitstring"] == "1000"
    with pytest.raises(AlgorithmExecutionError):
        sampled_partition_result(MATRIX, ("1000", [0], [1, 2, 3], {}), runtime_seconds=0)


def test_mapped_inputs_run_all_three_existing_algorithms():
    """DTO에서 생성한 인자로 BF·SDP·QAOA를 실행하고 결과 형식을 비교한다."""
    # 요청을 매핑하고 고전 알고리즘 두 종류를 실행한다.
    inputs = MaxCutRequest(matrix=MATRIX, qaoa={"maxiter": 30, "shots": 64}).to_solver_inputs()
    exact = brute_force_max_cut(**inputs["brute_force"])
    sdp = goemans_williamson_max_cut(**inputs["sdp"])
    # QAOA 회로 생성·최적화·샘플링 후 공통 결과 자료형으로 변환한다.
    circuit, gamma, beta = build_qaoa_circuit(**inputs["qaoa_circuit"])
    operator, _ = build_maxcut_pauli_list(MATRIX)
    g, b, _, _ = optimize_qaoa_parameters(circuit, operator, **inputs["qaoa_optimizer"])
    sample = get_best_partition(circuit, gamma, beta, g, b, **inputs["qaoa_sampler"])
    quantum = sampled_partition_result(MATRIX, sample, runtime_seconds=0)
    # 세 알고리즘의 컷 값과 직렬화 형식이 공통 계약을 만족하는지 확인한다.
    for result in (exact, sdp, quantum):
        assert result.cut_value == cut_value(MATRIX, result.assignment)
        assert 0 <= result.cut_value <= exact.cut_value
        assert len(result.assignment) == 4
        assert set(result.to_dict() if hasattr(result, "to_dict") else result.model_dump()) >= {"algorithm", "assignment", "partition", "bitstring", "cut_value", "runtime_seconds"}
    assert exact.cut_value == 10
    assert sdp.cut_value == exact.cut_value


def test_preset_classical_agreement():
    """프리셋의 SDP 결과가 BF 최적값을 넘지 않으며 배정과 일치하는지 확인한다."""
    presets = json.loads((Path(__file__).resolve().parent.parent / "data/presets.json").read_text(encoding="utf-8-sig"))
    for preset in presets.values():
        matrix = preset["matrix"]
        exact = brute_force_max_cut(matrix)
        approx = goemans_williamson_max_cut(matrix)
        assert approx.cut_value <= exact.cut_value
        assert approx.cut_value == cut_value(matrix, approx.assignment)


# 잘못된 가중치와 행렬 구조에 대해 두 고전 알고리즘의 입력 거절을 확인한다.
@pytest.mark.parametrize("matrix", INVALID_MATRICES)
@pytest.mark.parametrize("solver", SOLVERS)
def test_classical_rejects_invalid_weights(solver, matrix):
    """두 고전 알고리즘이 공통 검증기를 통해 잘못된 입력을 거절하는지 확인한다."""
    with pytest.raises(ValueError):
        solver(matrix)


if __name__ == "__main__":
    print("=== 양자·고전 입출력 호환성 검증 시작 ===")
    cases = [
        ("해밀토니안과 실제 컷 값 일치", test_all_basis_energies_equal_classical_cut_with_offset, ()),
        ("비트스트링의 노드 순서 유지", test_node_order_mapping_without_double_reversal, ()),
        ("DTO로 세 알고리즘 실행", test_mapped_inputs_run_all_three_existing_algorithms, ()),
        ("프리셋의 BF·SDP 결과 비교", test_preset_classical_agreement, ()),
    ]
    # 파라미터 테스트도 일반 반복문으로 실행하여 누락 없이 결과를 확인한다.
    for solver in SOLVERS:
        for i, matrix in enumerate(INVALID_MATRICES, 1):
            cases.append((f"{solver.__name__} 잘못된 입력 거절 {i}",
                          test_classical_rejects_invalid_weights, (solver, matrix)))
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
    print(f"\n입출력 호환성 결과: 성공 {passed}개 / 실패 {failed}개")
    raise SystemExit(1 if failed else 0)
