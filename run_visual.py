# run_visual.py
import matplotlib.pyplot as plt
from visual.graph_view import GraphVisualizer

# 1. 테스트용 임시 JSON 데이터 만들기
import json
sample_data = {
    "num_nodes": 4,
    "edges": [
        {"source": 0, "target": 1, "weight": 1.0},
        {"source": 1, "target": 2, "weight": 3.0}, # 가중치가 커서 굵고 빨간 선
        {"source": 2, "target": 3, "weight": 1.5},
        {"source": 3, "target": 0, "weight": 0.5}  # 가중치가 작아서 얇고 옅은 선
    ]
}
with open("temp_test.json", "w") as f:
    json.dump(sample_data, f)

# 2. 시각화 컴포넌트 실행
viz = GraphVisualizer("temp_test.json")
fig = viz.draw_weighted_graph()

# 3. 화면에 띄우기
plt.show()