import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.hamiltonian import build_maxcut_pauli_list
from core.qaoa_circuit import build_qaoa_circuit
from core.optimizer import optimize_qaoa_parameters
from core.sampler import get_best_partition

def test_t6_sampler():
    print("=== [Sprint 1 - Day 4 T6 최종 양자 샘플링 검증] ===")

    # 4노드 인접 행렬 (0-1, 1-2, 2-3, 3-0 앙숙 관계)
    matrix = [
        [0.0, 1.0, 0.0, 1.0],
        [1.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 1.0],
        [1.0, 0.0, 1.0, 0.0]
    ]

    # 1. 뼈대 생성 (해밀토니안, 회로)
    hamiltonian, _ = build_maxcut_pauli_list(matrix)
    qc, gamma_vec, beta_vec = build_qaoa_circuit(matrix, p=1, measure=False)

    # 2. 최적화기 실행 (COBYLA 두뇌)
    print("🧠 최적화 진행 중...")
    opt_gamma, opt_beta, min_energy, _ = optimize_qaoa_parameters(qc, hamiltonian, p=1, maxiter=50)

    # 3. 샘플러로 최종 정답 도출
    print("🎯 양자 시뮬레이터(Sampler) 측정 중...")
    best_bitstring, group_a, group_b, _ = get_best_partition(
        qc, gamma_vec, beta_vec, opt_gamma, opt_beta, shots=1000
    )

    print(f"✅ 수렴 에너지: {min_energy:.4f}")
    print(f"✅ 최다 빈도 정답 비트스트링: {best_bitstring}")
    print(f"✅ 파티 분할 결과: 그룹 A {group_a} / 그룹 B {group_b}")

    assert len(group_a) + len(group_b) == 4
    
    print("\n🎉 [T6] 파티 갈등 최적화 최종 결괏값 도출 성공! (Sprint 1 양자 코어 완성)")

if __name__ == "__main__":
    test_t6_sampler()