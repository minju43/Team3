import json

def parse_to_adjacency_matrix(canvas_data: dict) -> str:
    """
    [US-06] 캔버스/사용자 그래프 데이터(dict)를 백엔드 규격 인접 행렬 JSON 문자열로 파싱하는 함수
    """
    nodes = canvas_data.get("nodes", [])
    edges = canvas_data.get("edges", [])
    
    num_nodes = len(nodes)
    
    # 1. N x N 크기의 0.0으로 채워진 2차원 배열(행렬) 초기화
    matrix = [[0.0 for _ in range(num_nodes)] for _ in range(num_nodes)]
    
    # 2. 엣지 정보를 순회하며 행렬에 가중치 매핑
    for edge in edges:
        u = int(edge["source"])
        v = int(edge["target"])
        weight = float(edge.get("weight", 1.0))  # 가중치가 없으면 기본값 1.0 적용
        
        # 유효한 노드 인덱스 범위 내이고 자기 자신으로의 루프가 아닐 때만 반영
        if 0 <= u < num_nodes and 0 <= v < num_nodes and u != v:
            matrix[u][v] = weight
            matrix[v][u] = weight
        
    # 3. 백엔드 API 스키마 규격("matrix")에 맞춰 JSON 포맷팅 반환
    result = {
        "num_nodes": num_nodes,
        "matrix": matrix
    }
    
    return json.dumps(result, indent=2)


# --- 단독 테스트 실행 코드 ---
if __name__ == "__main__":
    sample_canvas_data = {
        "nodes": [{"id": 0}, {"id": 1}, {"id": 2}],
        "edges": [
            {"source": 0, "target": 1, "weight": 2.5},
            {"source": 1, "target": 2, "weight": 1.0}
        ]
    }
    
    json_output = parse_to_adjacency_matrix(sample_canvas_data)
    print(json_output)