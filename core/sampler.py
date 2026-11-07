"""
QAOA 최적화 결과 샘플링 및 비트스트링 해석 모듈
Task ID: T6
"""
from typing import List, Tuple
from qiskit import QuantumCircuit
from qiskit.primitives import Sampler
from qiskit.circuit import ParameterVector
from core.qaoa_circuit import bind_qaoa_parameters

def get_best_partition(
    qc: QuantumCircuit,
    gamma_vec: ParameterVector,
    beta_vec: ParameterVector,
    opt_gamma: List[float],
    opt_beta: List[float],
    shots: int = 1000
) -> Tuple[str, List[int], List[int], dict]:
    """
    최적화된 파라미터를 회로에 바인딩하고 측정을 수행하여 최적의 파티션(비트스트링)을 반환합니다.
    """
    # 1. 최적화된 다이얼 각도 바인딩
    bound_qc = bind_qaoa_parameters(qc, gamma_vec, beta_vec, opt_gamma, opt_beta)
    
    # 측정 게이트가 없으면 끝에 추가
    if len(bound_qc.cregs) == 0:
        bound_qc.measure_all()
        
    # 2. Sampler(양자 시뮬레이터)로 회로 1000번 쏘기
    sampler = Sampler(options={"shots": shots})
    job = sampler.run(bound_qc)
    result = job.result()
    
    # 3. 확률 분포에서 1등 비트스트링(가장 많이 나온 정답) 추출
    quasi_dist = result.quasi_dists[0]
    best_int = max(quasi_dist, key=quasi_dist.get)
    
    # 정수를 이진수로 변환 (Qiskit은 큐비트 순서가 반대라 [::-1]로 리틀 엔디안 보정)
    n_qubits = bound_qc.num_qubits
    best_bitstring = format(best_int, f'0{n_qubits}b')[::-1]
    
    # 4. 비트스트링 기반 노드 분할 (0은 그룹 A, 1은 그룹 B)
    group_a = []
    group_b = []
    for node, bit in enumerate(best_bitstring):
        if bit == '0':
            group_a.append(node)
        else:
            group_b.append(node)
            
    return best_bitstring, group_a, group_b, quasi_dist