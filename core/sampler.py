"""
QAOA 최적화 결과 샘플링, 비트스트링 해석 및 M3 판독 오류 완화 모듈
Task ID: T6, US-03, US-04, US-12
"""
from typing import List, Tuple
from qiskit import QuantumCircuit, transpile
from qiskit_aer.primitives import Sampler as IdealSampler
from qiskit.circuit import ParameterVector
import mthree

from core.qaoa_circuit import bind_qaoa_parameters
from core.backend_manager import QuantumBackendManager


def get_best_partition(
    qc: QuantumCircuit,
    gamma_vec: ParameterVector,
    beta_vec: ParameterVector,
    opt_gamma: List[float],
    opt_beta: List[float],
    shots: int = 1000,
    mode: str = "ideal",
    gate_error: float = 0.01,
    readout_error: float = 0.03,
    apply_m3: bool = False
) -> Tuple[str, List[int], List[int], dict]:
    """
    최적화된 파라미터를 회로에 바인딩하고 측정을 수행하여 최적의 파티션(비트스트링)을 반환합니다.
    - mode: 'ideal' | 'noisy_sim' | 'real_qpu'
    - apply_m3: True 설정 시 M3(Matrix-free Measurement Mitigation) 판독 오차 보정 적용 (US-04)
    """
    # 1. 최적화된 다이얼 각도 바인딩
    bound_qc = bind_qaoa_parameters(qc, gamma_vec, beta_vec, opt_gamma, opt_beta)
    n_qubits = bound_qc.num_qubits

    # 측정 게이트가 없으면 끝에 추가
    if len(bound_qc.cregs) == 0:
        bound_qc.measure_all()

    # 2. 모드에 따른 샘플링 및 M3 오류 완화 분기
    if mode == "ideal":
        sampler = IdealSampler(run_options={"shots": shots})
        job = sampler.run(bound_qc)
        result = job.result()
        quasi_dist = dict(result.quasi_dists[0])
    else:
        # 노이즈 시뮬레이터 또는 실제 QPU 백엔드 로드
        manager = QuantumBackendManager()
        backend = manager.get_backend(
            mode=mode,
            gate_error=gate_error,
            readout_error=readout_error
        )

        # 백엔드 하드웨어 게이트에 맞게 회로 변환(Transpile) 후 실행
        transpiled_qc = transpile(bound_qc, backend)
        job = backend.run(transpiled_qc, shots=shots)
        raw_counts = job.result().get_counts()

        if apply_m3:
            # [US-04] M3(Matrix-free Measurement Mitigation) 판독 오차 보정 수행
            mit = mthree.M3Mitigation(backend)
            mit.cals_from_system(range(n_qubits))
            m3_quasi = mit.apply_correction(raw_counts, range(n_qubits))

            # 기존 포맷(정수 키: 확률)과 100% 호환되도록 변환 (음수 준확률은 0으로 클리핑 후 정규화)
            quasi_dist = {}
            for bitstr, prob in m3_quasi.items():
                clean_bitstr = bitstr.replace(" ", "")
                quasi_dist[int(clean_bitstr, 2)] = max(0.0, float(prob))
            
            total_prob = sum(quasi_dist.values())
            if total_prob > 0:
                quasi_dist = {k: round(v / total_prob, 6) for k, v in quasi_dist.items()}
        else:
            # 보정 전 Raw 노이즈 카운트를 기존과 동일한 정수 키 확률 분포로 변환
            quasi_dist = {
                int(bitstr.replace(" ", ""), 2): round(count / shots, 6)
                for bitstr, count in raw_counts.items()
            }

    # 3. 확률 분포에서 1등 비트스트링(가장 많이 나온 정답) 추출
    best_int = max(quasi_dist, key=quasi_dist.get)

    # 정수를 이진수로 변환 (Qiskit은 큐비트 순서가 반대라 [::-1]로 리틀 엔디안 보정)
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