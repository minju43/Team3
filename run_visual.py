# run_visual.py
import matplotlib.pyplot as plt
from visual.graph_view import GraphVisualizer

# 1. 시각화 컴포넌트 로드 (T20-2에서 만든 temp_test.json 그대로 활용)
viz = GraphVisualizer("temp_test.json")

# 2. 가상의 Max-Cut 결과 비트스트링 (예: 0번/3번 노드는 '0' 그룹, 1번/2번 노드는 '1' 그룹)
best_partition = "0110" 
print(f"적용된 분할 결과 비트스트링: {best_partition}")

# 3. 컬러 하이라이트가 적용된 분할 그래프 그리기
fig = viz.draw_partitioned_graph(best_partition)

# 4. 화면에 띄우기
plt.show()