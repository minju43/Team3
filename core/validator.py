from typing import List

class GraphValidationError(Exception):
    """그래프 유효성 검증 실패 시 발생하는 예외 클래스"""
    pass

def validate_adjacency_matrix(matrix: List[List[float]]) -> int:
    """
    인접 행렬의 유효성을 검증하고 노드 수(N)를 반환합니다.
    1. 데이터 빈값 및 타입 검증
    2. 노드 수 2개 이상 14개 이하 제한 (15개 이상 시 차단)
    3. 정사각 행렬(NxN) 검증
    4. 자기 루프(대각 성분 != 0) 차단
    5. 무향 그래프 대칭성 (A_ij == A_ji) 검증
    6. 음수 가중치 차단
    """
    if not matrix or not isinstance(matrix, list):
        raise GraphValidationError("입력된 인접 행렬 데이터가 올바르지 않습니다.")
        
    n = len(matrix)
    
    if n < 2:
        raise GraphValidationError("갈등 분할을 위해 최소 2개 이상의 노드가 필요합니다.")
    if n > 14:
        raise GraphValidationError(f"노드 수({n}개)가 너무 많습니다. 최대 14개 노드까지만 지원합니다.")
        
    for i in range(n):
        if len(matrix[i]) != n:
            raise GraphValidationError(f"{i}번째 행의 길이가 전체 노드 수({n})와 일치하지 않습니다.")
            
        for j in range(n):
            val = matrix[i][j]
            
            if not isinstance(val, (int, float)):
                raise GraphValidationError(f"위치 ({i}, {j})의 값이 유효한 숫자가 아닙니다.")
                
            if val < 0:
                raise GraphValidationError(f"위치 ({i}, {j})의 갈등 가중치는 음수일 수 없습니다: {val}")
                
            if i == j and val != 0:
                raise GraphValidationError(f"노드 {i}의 자기 자신에 대한 갈등 값은 0이어야 합니다.")
                
            if matrix[i][j] != matrix[j][i]:
                raise GraphValidationError(f"대칭 행렬이 아닙니다: ({i},{j})={matrix[i][j]} != ({j},{i})={matrix[j][i]}")
                
    return n
