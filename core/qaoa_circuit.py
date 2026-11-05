"""
Max-Cut QAOA 파라미터화 양자 회로(Ansatz) 생성 모듈
Task ID: T4
"""
from typing import List, Tuple, Optional
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from core.validator import validate_adjacency_matrix


def build_qaoa_circuit(
    matrix: List[List[float]], 
    p: int = 1,
    measure: bool = False
) -> Tuple[QuantumCircuit, ParameterVector, ParameterVector]:
    """
    N x N 인접 행렬과 레이어 수(p)를 받아 파라미터화된 QAOA 양자 회로를 생성합니다.

    회로 구조:
      1. 초기화: 모든 큐비트에 Hadamard Gate 적용 (|+>^{\otimes n})
      2. p개 레이어 반복:
         - Problem Unitary U(C, gamma): 엣지 (i, j)마다 RZZ(-w * gamma) 적용
         - Mixer Unitary U(B, beta): 각 큐비트마다 RX(2 * beta) 적용
      3. (선택) 고전 레지스터 측정 게이트 추가

    Args:
        matrix: N x N 무향 가중치 인접 행렬
        p: QAOA 레이어 반복 수 (기본값: 1)
        measure: True일 경우 측정(measure_all)을 회로 끝에 추가

    Returns:
        qc: 파라미터화된 QuantumCircuit
        gamma: ParameterVector (길이 p)
        beta: ParameterVector (길이 p)
    """
    validate_adjacency_matrix(matrix)
    n_qubits = len(matrix)

    qc = QuantumCircuit(n_qubits, name=f"QAOA_p{p}")

    # 1. 초기 균등 중첩 상태: |+>
    qc.h(range(n_qubits))
    qc.barrier()

    # 파라미터 벡터 정의
    gamma = ParameterVector("gamma", p)
    beta = ParameterVector("beta", p)

    # 2. QAOA 레이어 구성
    for layer in range(p):
        # (1) 비용 유니터리 U(C, gamma)
        for i in range(n_qubits):
            for j in range(i + 1, n_qubits):
                w = matrix[i][j]
                if w != 0:
                    # RZZ(theta) = exp(-i * theta/2 * Z_i Z_j)
                    # H_C 항의 exp(-i * (-w/2 * Z_i Z_j) * gamma) = exp(i * w * gamma / 2 * Z_i Z_j)
                    # 따라서 theta = -w * gamma
                    qc.rzz(-w * gamma[layer], i, j)

        qc.barrier()

        # (2) 믹서 유니터리 U(B, beta)
        for i in range(n_qubits):
            qc.rx(2 * beta[layer], i)

        qc.barrier()

    # 3. 측정 게이트 (Shot 기반 샘플링용)
    if measure:
        qc.measure_all()

    return qc, gamma, beta


def bind_qaoa_parameters(
    qc: QuantumCircuit,
    gamma_vec: ParameterVector,
    beta_vec: ParameterVector,
    gamma_vals: List[float],
    beta_vals: List[float]
) -> QuantumCircuit:
    """
    파라미터화된 회로에 실제 수치 각도(gamma, beta)를 바인딩하여 실행 가능한 회로를 반환합니다.
    """
    param_dict = {}
    for g_param, g_val in zip(gamma_vec, gamma_vals):
        param_dict[g_param] = g_val
    for b_param, b_val in zip(beta_vec, beta_vals):
        param_dict[b_param] = b_val

    return qc.assign_parameters(param_dict)