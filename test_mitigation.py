# test_mitigation.py
import numpy as np
from core.hamiltonian import build_maxcut_pauli_list
from core.qaoa_circuit import build_qaoa_circuit, bind_qaoa_parameters
from core.optimizer import optimize_qaoa_parameters
from core.sampler import get_best_partition
from core.mitigation import run_zne_estimator

# 1. 테스트용 4노드 가중치 인접 행렬 (최적 Cut = 14, 정답 비트스트링 = 0110 또는 1001)
matrix = [
    [0.0, 5.0, 2.0, 1.0],
    [5.0, 0.0, 0.0, 3.0],
    [2.0, 0.0, 0.0, 4.0],
    [1.0, 3.0, 4.0, 0.0]
]
p = 3
shots = 2000

# 효과를 극적으로 보기 위해 게이트 에러 2%, 판독(Readout) 에러 8%로 노이즈 설정
gate_err = 0.02
readout_err = 0.08

print("=== [1] 해밀토니안 및 QAOA 회로(p=3) 생성 ===")
hamiltonian, offset = build_maxcut_pauli_list(matrix)

# 인접 행렬(matrix)을 직접 전달하여 회로와 파라미터 벡터 생성
qc, gamma_vec, beta_vec = build_qaoa_circuit(matrix, p=p)

# Ideal 환경 기준점 확인
opt_g_ideal, opt_b_ideal, ideal_energy, _ = optimize_qaoa_parameters(
    qc, hamiltonian, p=p, maxiter=50, mode="ideal"
)
print(f"▶ [Ideal (무오류)] 최적 에너지: {ideal_energy:.4f} (예상 Cut: {ideal_energy + offset:.2f})\n")

print("=== [2] Noisy 시뮬레이터 최적화 (US-03, US-12) ===")
opt_g, opt_b, noisy_energy, _ = optimize_qaoa_parameters(
    qc, hamiltonian, p=p, maxiter=50,
    mode="noisy_sim", gate_error=gate_err, readout_error=readout_err, shots=shots
)
print(f"▶ [Raw Noisy] 노이즈 낀 에너지: {noisy_energy:.4f} (예상 Cut: {noisy_energy + offset:.2f})\n")

print("=== [3] M3 판독 오류 완화 검증 (US-04: Raw vs M3) ===")
# 3-1. M3 보정 전 (Raw Noisy)
raw_bit, _, _, raw_dist = get_best_partition(
    qc, gamma_vec, beta_vec, opt_g, opt_b,
    shots=shots, mode="noisy_sim", gate_error=gate_err, readout_error=readout_err, apply_m3=False
)
raw_ans_prob = raw_dist.get(6, 0.0) + raw_dist.get(9, 0.0)

# 3-2. M3 보정 후 (Mitigated)
m3_bit, _, _, m3_dist = get_best_partition(
    qc, gamma_vec, beta_vec, opt_g, opt_b,
    shots=shots, mode="noisy_sim", gate_error=gate_err, readout_error=readout_err, apply_m3=True
)
m3_ans_prob = m3_dist.get(6, 0.0) + m3_dist.get(9, 0.0)

print(f"▶ [보정 전 Raw] 1등 비트스트링: {raw_bit} | 정답(0110/1001) 합산 확률: {raw_ans_prob*100:.1f}%")
print(f"▶ [보정 후 M3 ] 1등 비트스트링: {m3_bit} | 정답(0110/1001) 합산 확률: {m3_ans_prob*100:.1f}%\n")

print("=== [4] ZNE 게이트 오류 외삽 보정 검증 (US-04) ===")
bound_qc = bind_qaoa_parameters(qc, gamma_vec, beta_vec, opt_g, opt_b)
zne_res = run_zne_estimator(
    bound_qc, hamiltonian,
    scale_factors=[1, 3, 5],
    gate_error=gate_err, readout_error=readout_err, shots=shots
)
print(f"▶ 폴딩 배수(1x, 3x, 5x)별 측정 에너지: {zne_res['noisy_energies']}")
print(f"▶ 보정 전 에너지(1x): {zne_res['raw_noisy_energy']:.4f} (Cut 환산: {zne_res['raw_noisy_energy'] + offset:.2f})")
print(f"▶ ZNE 선형 보정 에너지: {zne_res['zne_linear_energy']:.4f} (Cut 환산: {zne_res['zne_linear_energy'] + offset:.2f})")
print(f"▶ ZNE Richardson 에너지: {zne_res['zne_richardson_energy']:.4f} (Cut 환산: {zne_res['zne_richardson_energy'] + offset:.2f})")