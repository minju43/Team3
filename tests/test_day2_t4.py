import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import json
from core.qaoa_circuit import build_qaoa_circuit, bind_qaoa_parameters


def test_t4_qaoa_ansatz():
    print("=== [Sprint 1 - Day 2 T4 QAOA 회로 생성 및 파라미터 바인딩 검증] ===")

    # 1. presets.json 로드
    with open("data/presets.json", "r", encoding="utf-8-sig") as f:
        presets = json.load(f)

    # 4노드 행렬 탐색
    matrix_4 = None
    for k, v in presets.items():
        m = v.get("matrix") if isinstance(v, dict) else v
        if isinstance(m, list) and len(m) == 4:
            matrix_4 = m
            break

    if matrix_4 is None:
        matrix_4 = [
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.0]
        ]

    # 2. p=1 회로 검증
    qc_p1, gamma_p1, beta_p1 = build_qaoa_circuit(matrix_4, p=1, measure=False)
    print(f"✅ p=1 회로 큐비트 수: {qc_p1.num_qubits} (기대값: 4)")
    print(f"✅ p=1 회로 파라미터 수: {qc_p1.num_parameters} (기대값: 2)")
    assert qc_p1.num_qubits == 4
    assert qc_p1.num_parameters == 2

    # 3. p=2 회로 검증
    qc_p2, gamma_p2, beta_p2 = build_qaoa_circuit(matrix_4, p=2, measure=True)
    print(f"✅ p=2 회로 파라미터 수: {qc_p2.num_parameters} (기대값: 4)")
    assert qc_p2.num_parameters == 4

    # 4. 수치 파라미터 바인딩(Assign) 검증
    bound_qc = bind_qaoa_parameters(
        qc_p1, 
        gamma_p1, 
        beta_p1, 
        gamma_vals=[0.392], 
        beta_vals=[0.785]
    )
    print(f"✅ 바인딩 후 미할당 파라미터 수: {bound_qc.num_parameters} (기대값: 0)")
    assert bound_qc.num_parameters == 0

    print("\n🎉 [T4] QAOA 파라미터화 회로 및 바인딩 모듈 검증 성공!")


if __name__ == "__main__":
    test_t4_qaoa_ansatz()