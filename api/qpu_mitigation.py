"""실제 QPU의 물리 회로 폴딩과 컷 기댓값 계산."""

from math import fsum

import numpy as np

from .errors import AlgorithmExecutionError


def build_folded_measurements(measured, backend, scales):
    """같은 물리 회로를 폴딩하고 원래의 측정 매핑을 유지한다."""
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    unitary = measured.remove_final_measurements(inplace=False)
    # 물리 큐비트 배치를 변경하지 않고 역회로의 게이트만 장비 기저로 변환한다.
    translation = generate_preset_pass_manager(backend=backend, optimization_level=0).translation
    inverse = translation.run(unitary.inverse())
    for item in inverse.data:
        if item.operation.name == "barrier":
            continue
        qubits = tuple(inverse.find_bit(qubit).index for qubit in item.qubits)
        if not backend.target.instruction_supported(operation_name=item.operation.name, qargs=qubits):
            raise AlgorithmExecutionError("역회로를 원래 물리 큐비트 배치에서 실행할 수 없습니다.")
    active_indices = sorted({unitary.find_bit(qubit).index for item in unitary.data
                             if item.operation.name != "barrier" for qubit in item.qubits})

    circuits = {1: measured}
    for scale in scales[1:]:
        folded = measured.copy_empty_like()
        for _ in range((scale - 1) // 2):
            folded.compose(unitary, inplace=True)
            folded.barrier(*active_indices)
            folded.compose(inverse, inplace=True)
            folded.barrier(*active_indices)
        folded.compose(measured, inplace=True)
        circuits[scale] = folded
    return circuits


def expected_cut(matrix, weights):
    """Qiskit 비트 순서의 확률 또는 준확률로 컷 기댓값을 구한다."""
    n = len(matrix)
    edges = [(i, j, matrix[i][j]) for i in range(n) for j in range(i + 1, n) if matrix[i][j]]
    contributions = []
    for bits, weight in weights.items():
        if len(bits) != n or any(bit not in "01" for bit in bits):
            raise AlgorithmExecutionError("측정 비트열과 그래프 노드 수가 일치하지 않습니다.")
        contributions.append(weight * fsum(w for i, j, w in edges if bits[n - i - 1] != bits[n - j - 1]))
    return fsum(contributions)


def extrapolate_linear(scales, values):
    """미리 정한 선형 회귀의 절편을 제한 없이 반환한다."""
    return float(np.polynomial.polynomial.polyfit(scales, values, deg=1)[0])
