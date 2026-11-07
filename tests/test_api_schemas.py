"""입력 DTO의 프리셋 호환성, 입력 검증, 알고리즘별 인자 매핑을 검증한다."""
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# 기존 테스트와 같이 프로젝트 모듈을 직접 불러올 수 있도록 경로를 추가한다.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.schemas import MaxCutRequest
from core.validator import validate_adjacency_matrix


# pytest와 파일 직접 실행에서 동일한 테스트 입력을 사용한다.
INVALID_INPUTS = [
    {"matrix": []}, {"matrix": [[0]]}, {"matrix": [[0, 1], [1]]},
    {"matrix": [[0, 2], [1, 0]]}, {"matrix": [[1, 0], [0, 0]]},
    {"matrix": [[0, -1], [-1, 0]]}, {"matrix": [[0, float("nan")], [float("nan"), 0]]},
    {"matrix": [[0, float("inf")], [float("inf"), 0]]},
    {"matrix": [[0, True], [True, 0]]}, {"matrix": [[0, "1"], ["1", 0]]},
    {"matrix": [[0, 1], [1, 0]], "num_nodes": 3},
    {"matrix": [[0] * 15 for _ in range(15)]},
    {"matrix": [[0, 1], [1, 0]], "qaoa": {"shots": 0}},
    {"matrix": [[0, 1], [1, 0]], "qaoa": {"p": True}},
    {"matrix": [[0, 1], [1, 0]], "sdp": {"rounds": 1.5}},
    {"matrix": [[0, 1], [1, 0]], "sdp": {"seed": -1}},
    {"matrix": [[0, 1], [1, 0]], "unknown": 1},
]


def test_presets_and_independent_solver_mapping():
    """모든 프리셋이 파싱되며 각 알고리즘에 독립된 행렬이 전달되는지 확인한다."""
    presets = json.loads((Path(__file__).resolve().parent.parent / "data/presets.json").read_text(encoding="utf-8-sig"))
    for preset in presets.values():
        request = MaxCutRequest.model_validate(preset)
        inputs = request.to_solver_inputs()
        assert validate_adjacency_matrix(inputs["qaoa_circuit"]["matrix"]) == preset["num_nodes"]
        assert inputs["qaoa_sampler"] == {"shots": 1024}
        # 한 알고리즘의 입력을 바꿔도 원본과 다른 알고리즘의 입력은 유지되어야 한다.
        inputs["brute_force"]["adjacency"][0][1] = 999
        assert request.matrix[0][1] != 999
        assert inputs["sdp"]["adjacency"][0][1] != 999
        assert MaxCutRequest.model_validate_json(request.model_dump_json()) == request


# 잘못된 그래프, 노드 수, 실행 옵션, 미정의 필드가 모두 거절되는지 확인한다.
@pytest.mark.parametrize("payload", INVALID_INPUTS)
def test_reject_invalid_inputs(payload):
    """잘못된 요청에 대해 Pydantic 검증 예외가 발생하는지 확인한다."""
    with pytest.raises(ValidationError):
        MaxCutRequest.model_validate(payload)


def test_roundoff_uses_exact_core_symmetry():
    """DTO도 공통 코어 기준에 따라 미세한 차이가 있는 비대칭 행렬을 거절한다."""
    with pytest.raises(ValidationError):
        MaxCutRequest(matrix=[[0, 1], [1 + 1e-12, 0]])


if __name__ == "__main__":
    print("=== 입력 DTO 검증 시작 ===")
    # 기존 assert 검증을 그대로 실행하고 항목별 결과를 출력한다.
    cases = [
        ("프리셋 파싱 및 독립된 인자 매핑", test_presets_and_independent_solver_mapping, ()),
        ("코어의 정확한 대칭성 기준 적용", test_roundoff_uses_exact_core_symmetry, ()),
    ]
    cases += [(f"잘못된 입력 거절 {i}", test_reject_invalid_inputs, (payload,))
              for i, payload in enumerate(INVALID_INPUTS, 1)]
    passed = failed = 0
    for label, test, args in cases:
        try:
            test(*args)
        except (Exception, pytest.fail.Exception) as exc:
            failed += 1
            print(f"[실패] {label}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[성공] {label}")
    print(f"\n입력 DTO 결과: 성공 {passed}개 / 실패 {failed}개")
    raise SystemExit(1 if failed else 0)
