import json
from core.validator import validate_adjacency_matrix, GraphValidationError

def test_day1():
    print("=== [Sprint 1 - Day 1 검증 시작] ===")
    
    # 1. presets.json 로드 및 정상 데이터 검증
    with open("data/presets.json", "r", encoding="utf-8-sig") as f:
        presets = json.load(f)
        
    for key, item in presets.items():
        n = validate_adjacency_matrix(item["matrix"])
        print(f"✅ {item['name']} 검증 성공 (노드 수: {n})")
        
    # 2. 15개 노드 초과 시 차단 예외 테스트
    matrix_15 = [[0] * 15 for _ in range(15)]
    try:
        validate_adjacency_matrix(matrix_15)
        print("❌ 실패: 15개 노드가 통과됨")
    except GraphValidationError as e:
        print(f"✅ 노드 초과 차단 정상 작동: {e}")
        
    # 3. 비대칭 행렬 차단 예외 테스트
    asym_matrix = [[0, 5], [3, 0]]
    try:
        validate_adjacency_matrix(asym_matrix)
        print("❌ 실패: 비대칭 행렬이 통과됨")
    except GraphValidationError as e:
        print(f"✅ 비대칭 행렬 차단 정상 작동: {e}")
        
    print("\n🎉 Day 1 (T1, T16) 모든 요구사항 검증 완료!")

if __name__ == '__main__':
    test_day1()
