"""
Max-Cut QAOA 파라미터화 양자 회로(Ansatz) 생성 모듈
Task ID: T4
"""
from typing import List, Tuple
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from core.validator import validate_adjacency_matrix


def build_qaoa_circuit(
    matrix: List[List[float]], 
    p: int = 1,
    measure: bool = False
) -> Tuple[QuantumCircuit, ParameterVector, ParameterVector]:
    validate_adjacency_matrix(matrix)
    n_qubits = len(matrix)

    qc = QuantumCircuit(n_qubits, name=f"QAOA_p{p}")
    qc.h(range(n_qubits))
    qc.barrier()

    gamma = ParameterVector("gamma", p)
    beta = ParameterVector("beta", p)

    for layer in range(p):
        for i in range(n_qubits):
            for j in range(i + 1, n_qubits):
                w = matrix[i][j]
                if w != 0:
                    # [버그 수정] -w가 아니라 2*w로 스케일과 방향을 맞춤!
                    qc.rzz(2 * w * gamma[layer], i, j)
        qc.barrier()

        for i in range(n_qubits):
            qc.rx(2 * beta[layer], i)
        qc.barrier()

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
    param_dict = {}
    for g_param, g_val in zip(gamma_vec, gamma_vals):
        param_dict[g_param] = g_val
    for b_param, b_val in zip(beta_vec, beta_vals):
        param_dict[b_param] = b_val

    return qc.assign_parameters(param_dict)