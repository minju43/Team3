import json

def parse_to_adjacency_matrix(canvas_data: dict) -> str:
    """
    [US-06] 캔버스 그래프 데이터(dict)를 인접 행렬 JSON 문자열로 파싱하는 함수
    """
    nodes = canvas_data.get("nodes", [])
    edges = canvas_data.get("edges", [])
    
    num_nodes = len(nodes)
    
    # 1. N x N 크기의 0.0으로 채워진 2차원 배열(행렬) 초기화
    matrix = [[0.0 for _ in range(num_nodes)] for _ in range(num_nodes)]
    
    # 2. 엣지 정보를 순회하며 행렬에 가중치 매핑
    for edge in edges:
        u = edge["source"]
        v = edge["target"]
        weight = edge.get("weight", 1.0)  # 가중치가 없으면 기본값 1.0 적용
        
        # Max-Cut 문제는 무방향 그래프이므로 양쪽에 모두 가중치를 넣어줍니다.
        matrix[u][v] = weight
        matrix[v][u] = weight
        
    # 3. 백엔드 API로 넘기기 좋게 JSON 형식으로 포맷팅하여 반환
    result = {
        "num_nodes": num_nodes,
        "adjacency_matrix": matrix
    }
    
    return json.dumps(result, indent=2)

# --- 테스트 실행 코드 ---
if __name__ == "__main__":
    sample_canvas_data = {
        "nodes": [{"id": 0}, {"id": 1}, {"id": 2}],
        "edges": [
            {"source": 0, "target": 1, "weight": 2.5},
            {"source": 1, "target": 2, "weight": 1.0}
        ]
    }
    
    json_output = parse_to_adjacency_matrix(sample_canvas_data)
    
    # 여기서부터 수정! (출력용으로만 예쁘게 포맷팅)
    parsed = json.loads(json_output)
    
    print("{")
    print(f'  "num_nodes": {parsed["num_nodes"]},')
    print('  "adjacency_matrix": [')
    
    matrix = parsed["adjacency_matrix"]
    for i, row in enumerate(matrix):
        comma = "," if i < len(matrix) - 1 else ""
        print(f"    {row}{comma}")
        
    print("  ]")
    print("}")