"""
Max-Cut 문제를 Ising 비용 해밀토니안(SparsePauliOp)으로 변환하는 모듈
Task ID: T3
"""
from typing import List, Tuple
import numpy as np
from qiskit.quantum_info import SparsePauliOp
from core.validator import validate_adjacency_matrix


def build_maxcut_pauli_list(matrix: List[List[float]]) -> Tuple[SparsePauliOp, float]:
    """
    인접 행렬을 입력받아 Max-Cut Ising 해밀토니안(SparsePauliOp)과 상수 오프셋을 반환합니다.

    H_C = sum_{i < j} (w_{ij} / 2) * (I - Z_i Z_j)
        = offset * I - sum_{i < j} (w_{ij} / 2) * Z_i Z_j

    Args:
        matrix: N x N 무향 가중치 인접 행렬

    Returns:
        hamiltonian: Qiskit SparsePauliOp 객체 (Z_i Z_j 상호작용 항)
        offset: 해밀토니안 상수 오프셋 (sum w_ij / 2)
    """
    # 1. 입력 유효성 검증 (T1 모듈 활용)
    validate_adjacency_matrix(matrix)

    n_nodes = len(matrix)
    pauli_list = []
    offset = 0.0

    # 2. 모든 상삼각 행렬 엣지 (i < j) 탐색
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            weight = matrix[i][j]
            if weight == 0:
                continue

            # 상수 오프셋 누적: w_ij / 2
            offset += weight / 2.0

            # 파울리 Z 연산자 문자열 생성
            # Qiskit 파울리 문자열은 역순(Little-endian) 인덱싱: [q_{N-1}, ..., q_1, q_0]
            pauli_chars = ["I"] * n_nodes
            pauli_chars[n_nodes - 1 - i] = "Z"
            pauli_chars[n_nodes - 1 - j] = "Z"
            pauli_str = "".join(pauli_chars)

            # Max-Cut 최소화 목적함수에 맞춘 가중치: -w_ij / 2
            pauli_coeff = -weight / 2.0
            pauli_list.append((pauli_str, pauli_coeff))

    # 엣지가 없는 빈 그래프 처리
    if not pauli_list:
        return SparsePauliOp.from_list([("I" * n_nodes, 0.0)]), 0.0

    hamiltonian = SparsePauliOp.from_list(pauli_list).simplify()
    return hamiltonian, offset