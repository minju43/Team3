import streamlit as st
import matplotlib.pyplot as plt
import networkx as nx

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="Q-PartyCut 대시보드", layout="wide")
st.title("Q-PartyCut: 양자 갈등 최적화 시뮬레이터")

st.info("US-06: 캔버스 데이터 파싱 기능 구현 완료 (visual/parser.py 적용 대기 중)")
st.divider()

# ==========================================
# [US-07] 파티 2분할 공간 시각화 (하이라이트 UI)
# ==========================================
st.subheader("🕸️ [US-07] 파티 분할 결과 시각화")

# 테스트용 가상 데이터 (나중에는 캔버스에서 직접 입력받은 데이터로 교체됨)
nodes = [0, 1, 2, 3]
edges = [(0, 1), (0, 2), (1, 3), (2, 3)]

# 백엔드 API에서 넘겨받았다고 가정하는 Max-Cut 결과 비트스트링
# (0번, 3번 노드가 A그룹(0) / 1번, 2번 노드가 B그룹(1))
mock_bitstring = "0110" 

if st.button("2분할 하이라이트 실행"):
    # 1. 그래프 기초 세팅
    G = nx.Graph()
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)

    pos = nx.spring_layout(G, seed=42)
    fig, ax = plt.subplots(figsize=(6, 5))

    # 2. 결과 비트스트링 기반 노드 색상 분할 (0은 빨강, 1은 파랑)
    node_colors = ["#ff4b4b" if mock_bitstring[n] == '0' else "#1f77b4" for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=600, ax=ax)
    nx.draw_networkx_labels(G, pos, font_color="white", font_weight="bold", ax=ax)

    # 3. 엣지 컷팅 판별 및 스타일링
    cut_edges = []
    normal_edges = []
    
    for u, v in G.edges():
        if mock_bitstring[u] != mock_bitstring[v]:
            cut_edges.append((u, v))  # 서로 다른 그룹을 잇는 엣지 (잘림)
        else:
            normal_edges.append((u, v)) # 같은 그룹을 잇는 엣지 (안 잘림)

    # 같은 파티끼리의 엣지는 얇은 회색 실선
    nx.draw_networkx_edges(G, pos, edgelist=normal_edges, edge_color="gray", alpha=0.5, ax=ax)
    # 끊어진(분할된) 갈등 엣지는 굵은 붉은 점선으로 하이라이트
    nx.draw_networkx_edges(G, pos, edgelist=cut_edges, edge_color="red", style="dashed", width=2.5, ax=ax)

    st.pyplot(fig)