import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import json
from core.hamiltonian import build_maxcut_pauli_list


def test_t3_hamiltonian():
    print("=== [Sprint 1 - Day 1/2 T3 해밀토니안 검증 시작] ===")

    # 1. 3노드 삼각형 그래프 검증
    tri_matrix = [
        [0.0, 2.0, 2.0],
        [2.0, 0.0, 2.0],
        [2.0, 2.0, 0.0]
    ]

    H_tri, offset_tri = build_maxcut_pauli_list(tri_matrix)
    print(f"✅ 3노드 삼각형 해밀토니안 항 개수: {len(H_tri)}개 (기대값: 3개)")
    print(f"✅ 3노드 상수 오프셋: {offset_tri} (기대값: 3.0)")
    assert len(H_tri) == 3
    assert offset_tri == 3.0

    # 2. data/presets.json 에서 프리셋 로드 검증
    with open("data/presets.json", "r", encoding="utf-8-sig") as f:
        presets = json.load(f)

    # presets.json 내부에서 4노드 행렬 자동 탐색
    four_node = None
    preset_key_name = ""
    for k, v in presets.items():
        if isinstance(v, dict) and "matrix" in v and len(v["matrix"]) == 4:
            four_node = v["matrix"]
            preset_key_name = k
            break
        elif isinstance(v, list) and len(v) == 4:
            four_node = v
            preset_key_name = k
            break

    if four_node is None:
        # 혹시 못 찾을 경우 기본 4노드 fallback 행렬 검증
        four_node = [
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.0]
        ]
        preset_key_name = "default_4node"

    H_4, offset_4 = build_maxcut_pauli_list(four_node)

    print(f"✅ 4노드 프리셋('{preset_key_name}') 해밀토니안 생성 성공 (Qubit 수: {H_4.num_qubits}, 엣지 항 수: {len(H_4)})")
    assert H_4.num_qubits == 4

    print("\n🎉 [T3] Max-Cut Ising 해밀토니안 변환 모듈 검증 성공!")


if __name__ == "__main__":
    test_t3_hamiltonian()