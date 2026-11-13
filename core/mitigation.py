"""
ZNE (Zero-Noise Extrapolation) 게이트 오류 완화 모듈
Task ID: US-04
"""
from typing import List, Dict, Any
import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer.primitives import Estimator as AerEstimator
from core.backend_manager import QuantumBackendManager


def fold_circuit_globally(qc: QuantumCircuit, scale_factor: int) -> QuantumCircuit:
    """
    ZNE를 위해 양자 회로를 홀수 배수(1, 3, 5...)로 전역 폴딩(U -> U * U^dagger * U)하여
    논리적 연산은 그대로 유지하면서 물리적 게이트 노이즈만 증폭시킵니다.
    """
    if scale_factor == 1:
        return qc.copy()
    if scale_factor % 2 == 0 or scale_factor < 1:
        raise ValueError("ZNE 폴딩 배수(scale_factor)는 1 이상의 홀수(1, 3, 5...)여야 합니다.")

    # 측정 게이트가 섞여 있으면 제거한 순수 연산 회로만 추출
    clean_qc = qc.remove_final_measurements(inplace=False)
    folded_qc = clean_qc.copy()
    inv_qc = clean_qc.inverse()

    num_folds = (scale_factor - 1) // 2
    for _ in range(num_folds):
        folded_qc.barrier()
        folded_qc.compose(inv_qc, inplace=True)
        folded_qc.barrier()
        folded_qc.compose(clean_qc, inplace=True)

    return folded_qc


def run_zne_estimator(
    bound_qc: QuantumCircuit,
    hamiltonian: SparsePauliOp,
    scale_factors: List[int] = [1, 3, 5],
    gate_error: float = 0.01,
    readout_error: float = 0.03,
    shots: int = 2048
) -> Dict[str, Any]:
    """
    [US-04] 노이즈 배율(1배, 3배, 5배)별로 기댓값을 측정한 뒤,
    영오차 지점(scale = 0.0)으로 외삽(Extrapolation)하여 보정된 에너지를 산출합니다.
    """
    manager = QuantumBackendManager()
    noise_model = manager.get_custom_noise_model(gate_error, readout_error)
    estimator = AerEstimator(
        backend_options={"noise_model": noise_model},
        run_options={"shots": shots}
    )

    noisy_energies = []
    for factor in scale_factors:
        folded = fold_circuit_globally(bound_qc, factor)
        job = estimator.run(folded, hamiltonian)
        energy = float(job.result().values[0])
        noisy_energies.append(energy)

    # 1차 선형 회귀 외삽 (Linear Extrapolation to scale=0)
    coeffs_linear = np.polyfit(scale_factors, noisy_energies, deg=1)
    zne_linear_energy = float(coeffs_linear[1])  # y절편 (x=0일 때의 값)

    # 2차 다항식(Richardson) 외삽 (점이 3개 이상일 때 곡선 추세 반영)
    if len(scale_factors) >= 3:
        coeffs_poly = np.polyfit(scale_factors, noisy_energies, deg=2)
        zne_richardson_energy = float(coeffs_poly[2])
    else:
        zne_richardson_energy = zne_linear_energy

    return {
        "scale_factors": scale_factors,
        "noisy_energies": [round(e, 6) for e in noisy_energies],
        "raw_noisy_energy": round(noisy_energies[0], 6),
        "zne_linear_energy": round(zne_linear_energy, 6),
        "zne_richardson_energy": round(zne_richardson_energy, 6)
    }