import streamlit as st
import matplotlib.pyplot as plt
import networkx as nx

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="Q-PartyCut 대시보드", layout="wide")
st.title("Q-PartyCut: 양자 갈등 최적화 시뮬레이터")

# ==========================================
# [US-09] 대표 갈등 시나리오 프리셋 원클릭 로더 UI
# ==========================================
st.sidebar.header("🎯 시나리오 프리셋 설정 (US-09)")
preset_choice = st.sidebar.selectbox(
    "대표 갈등 시나리오 선택",
    [
        "시나리오 1: 대립 구도 (N=4)",
        "시나리오 2: 삼각 동맹/갈등 (N=3)",
        "시나리오 3: 다선형 복잡 갈등 (N=5)"
    ]
)

# 프리셋별 갈등 그래프 데이터 및 결과 비트스트링 정의
if preset_choice == "시나리오 1: 대립 구도 (N=4)":
    nodes = [0, 1, 2, 3]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3)]
    mock_bitstring = "0110"
elif preset_choice == "시나리오 2: 삼각 동맹/갈등 (N=3)":
    nodes = [0, 1, 2]
    edges = [(0, 1), (1, 2), (2, 0)]
    mock_bitstring = "010"
else:  # 시나리오 3: 다선형 복잡 갈등 (N=5)
    nodes = [0, 1, 2, 3, 4]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4), (1, 3)]
    mock_bitstring = "01011"

st.sidebar.info(f"현재 선택된 프리셋: **{preset_choice}**\n- 노드 구성: {nodes}\n- 엣지 구성: {len(edges)}개")

st.divider()

# ==========================================
# [US-07] 파티 2분할 공간 시각화 (US-09 프리셋 연동)
# ==========================================
st.subheader(f"🕸️ [US-07 & US-09] 파티 분할 결과 시각화 ({preset_choice})")

if st.button("🚀 선택한 시나리오 2분할 실행"):
    # 1. 그래프 기초 세팅
    G = nx.Graph()
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)

    pos = nx.spring_layout(G, seed=42)
    fig, ax = plt.subplots(figsize=(6, 5))

    # 2. 비트스트링 기반 노드 색상 분할 (0은 빨강, 1은 파랑)
    node_colors = ["#ff4b4b" if mock_bitstring[n] == '0' else "#1f77b4" for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=600, ax=ax)
    nx.draw_networkx_labels(G, pos, font_color="white", font_weight="bold", ax=ax)

    # 3. 엣지 컷팅 판별 및 스타일링
    cut_edges = []
    normal_edges = []
    
    for u, v in G.edges():
        if u < len(mock_bitstring) and v < len(mock_bitstring):
            if mock_bitstring[u] != mock_bitstring[v]:
                cut_edges.append((u, v))  # 다른 파티 간 갈등 엣지 (잘림)
            else:
                normal_edges.append((u, v)) # 같은 파티 간 엣지 (안 잘림)
        else:
            normal_edges.append((u, v))

    # 같은 파티끼리의 엣지는 얇은 회색 실선
    nx.draw_networkx_edges(G, pos, edgelist=normal_edges, edge_color="gray", alpha=0.5, ax=ax)
    # 끊어진(분할된) 갈등 엣지는 굵은 붉은 점선으로 하이라이트
    nx.draw_networkx_edges(G, pos, edgelist=cut_edges, edge_color="red", style="dashed", width=2.5, ax=ax)

    st.pyplot(fig)
else:
    st.info("좌측 사이드바에서 시나리오를 변경하고 '선택한 시나리오 2분할 실행' 버튼을 눌러주세요.")