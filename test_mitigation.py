# test_mitigation.py
import numpy as np
import itertools
import time
from core.hamiltonian import build_maxcut_pauli_list
from core.qaoa_circuit import build_qaoa_circuit, bind_qaoa_parameters
from core.optimizer import optimize_qaoa_parameters
from core.sampler import get_best_partition
from core.mitigation import run_zne_estimator

def main():
    # 1. 테스트용 4노드 가중치 인접 행렬 (최적 Cut = 14)
    matrix = [
        [0.0, 5.0, 2.0, 1.0],
        [5.0, 0.0, 0.0, 3.0],
        [2.0, 0.0, 0.0, 4.0],
        [1.0, 3.0, 4.0, 0.0]
    ]
    
    # 노이즈 환경 설정 (기존 설정 유지)
    gate_err = 0.02
    readout_err = 0.08

    print("=== [1] 해밀토니안 생성 (1회만 실행) ===")
    hamiltonian, offset = build_maxcut_pauli_list(matrix)
    print(f"▶ Offset 값: {offset}\n")

    # 튜닝할 하이퍼파라미터 후보군
    p_candidates = [1, 2, 3]
    shots_candidates = [1024, 2000, 4096]
    zne_scale_factors = [[1, 3, 5], [1, 5, 9]]

    best_cut_value = -float('inf')
    best_params = {}
    
    total_combinations = len(p_candidates) * len(shots_candidates) * len(zne_scale_factors)
    current_idx = 1

    print("=== [2] M3/ZNE 하이퍼파라미터 튜닝(Grid Search) 시작 ===")
    print(f"총 {total_combinations}개의 조합을 탐색합니다. (에러율: Gate {gate_err*100}%, Readout {readout_err*100}%)\n")

    for p, shots, scales in itertools.product(p_candidates, shots_candidates, zne_scale_factors):
        print(f"[{current_idx}/{total_combinations}] 테스트 조합: p={p}, shots={shots}, zne_scales={scales}")
        start_time = time.time()
        
        # 1. QAOA 회로 생성
        qc, gamma_vec, beta_vec = build_qaoa_circuit(matrix, p=p)
        
        # 2. 파라미터 최적화 (Noisy)
        opt_g, opt_b, noisy_energy, _ = optimize_qaoa_parameters(
            qc, hamiltonian, p=p, maxiter=50,
            mode="noisy_sim", gate_error=gate_err, readout_error=readout_err, shots=shots
        )
        
        # 3. M3 판독 오류 완화 확률 검증
        m3_bit, _, _, m3_dist = get_best_partition(
            qc, gamma_vec, beta_vec, opt_g, opt_b,
            shots=shots, mode="noisy_sim", gate_error=gate_err, readout_error=readout_err, apply_m3=True
        )
        m3_ans_prob = m3_dist.get(6, 0.0) + m3_dist.get(9, 0.0)
        
        # 4. ZNE 게이트 오류 외삽 보정
        bound_qc = bind_qaoa_parameters(qc, gamma_vec, beta_vec, opt_g, opt_b)
        zne_res = run_zne_estimator(
            bound_qc, hamiltonian,
            scale_factors=scales,
            gate_error=gate_err, readout_error=readout_err, shots=shots
        )
        
        # Richardson 기반 복구된 Max-Cut 값 계산
        richardson_cut = zne_res['zne_richardson_energy'] + offset
        elapsed_time = time.time() - start_time
        
        print(f"  ➔ M3 보정 확률(0110/1001): {m3_ans_prob*100:.1f}%")
        print(f"  ➔ ZNE(Richardson) 복구 Cut: {richardson_cut:.4f} (소요시간: {elapsed_time:.1f}초)\n")
        
        # 최고 Cut 값 갱신
        if richardson_cut > best_cut_value:
            best_cut_value = richardson_cut
            best_params = {'p': p, 'shots': shots, 'zne_scales': scales}
            
        current_idx += 1

    print("==================================================")
    print("🏆 [튜닝 완료] 극한 노이즈 방어 최적 하이퍼파라미터")
    print("==================================================")
    print(f" - 최적 회로 깊이 (p): {best_params['p']}")
    print(f" - 최적 측정 횟수 (shots): {best_params['shots']}")
    print(f" - 최적 ZNE 외삽 배수: {best_params['zne_scales']}")
    print(f" - 도출된 최고 Max-Cut 값 (Richardson): {best_cut_value:.4f}")
    print("==================================================")

if __name__ == "__main__":
    main()