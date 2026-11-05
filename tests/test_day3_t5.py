import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.hamiltonian import build_maxcut_pauli_list
from core.qaoa_circuit import build_qaoa_circuit
from core.optimizer import optimize_qaoa_parameters

def test_t5_optimizer():
    print("=== [Sprint 1 - Day 3 T5 최적화 루프 연동 검증] ===")

    # 1. 간단한 4노드 그래프 인접 행렬
    matrix = [
        [0.0, 1.0, 0.0, 1.0],
        [1.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 1.0],
        [1.0, 0.0, 1.0, 0.0]
    ]

    # 2. 민주님이 어제오늘 만든 코어 모듈들 조립
    hamiltonian, offset = build_maxcut_pauli_list(matrix)
    qc, _, _ = build_qaoa_circuit(matrix, p=1, measure=False)

    # 3. 인공지능 선생님(COBYLA) 등판
    print("🧠 COBYLA 최적화 진행 중... (최대 100회 반복 탐색)")
    opt_gamma, opt_beta, min_energy, history = optimize_qaoa_parameters(
        qc, hamiltonian, p=1, maxiter=50
    )

    print(f"✅ 최적화 탐색 완료 (총 반복 횟수: {len(history)}회)")
    print(f"✅ 수렴된 최소 에너지(해밀토니안 기댓값): {min_energy:.4f}")
    print(f"✅ 최적의 다이얼 각도 (gamma): {opt_gamma}")
    print(f"✅ 최적의 다이얼 각도 (beta): {opt_beta}")

    assert len(history) > 1
    assert isinstance(min_energy, float)

    print("\n🎉 [T5] 양자-고전 하이브리드 알고리즘 두뇌 완성 성공!")


if __name__ == "__main__":
    test_t5_optimizer()