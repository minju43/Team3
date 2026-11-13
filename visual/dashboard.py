<<<<<<< HEAD
import streamlit as st
import pandas as pd
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
    mock_benchmarks = [
        {"algorithm": "Brute-Force", "max_cut_value": 18.5, "time": 0.05},
        {"algorithm": "SDP", "max_cut_value": 16.2, "time": 0.12},
        {"algorithm": "Raw QAOA", "max_cut_value": 17.0, "time": 1.50},
        {"algorithm": "Mitigated QAOA", "max_cut_value": 18.2, "time": 1.65}
    ]
elif preset_choice == "시나리오 2: 삼각 동맹/갈등 (N=3)":
    nodes = [0, 1, 2]
    edges = [(0, 1), (1, 2), (2, 0)]
    mock_bitstring = "010"
    mock_benchmarks = [
        {"algorithm": "Brute-Force", "max_cut_value": 12.0, "time": 0.02},
        {"algorithm": "SDP", "max_cut_value": 12.0, "time": 0.08},
        {"algorithm": "Raw QAOA", "max_cut_value": 10.5, "time": 1.10},
        {"algorithm": "Mitigated QAOA", "max_cut_value": 11.8, "time": 1.25}
    ]
else:  # 시나리오 3: 다선형 복잡 갈등 (N=5)
    nodes = [0, 1, 2, 3, 4]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4), (1, 3)]
    mock_bitstring = "01011"
    mock_benchmarks = [
        {"algorithm": "Brute-Force", "max_cut_value": 24.0, "time": 0.15},
        {"algorithm": "SDP", "max_cut_value": 21.5, "time": 0.20},
        {"algorithm": "Raw QAOA", "max_cut_value": 19.0, "time": 2.10},
        {"algorithm": "Mitigated QAOA", "max_cut_value": 22.8, "time": 2.30}
    ]

st.sidebar.info(f"선택된 프리셋: **{preset_choice}**\n- 노드: {nodes}\n- 엣지: {len(edges)}개")
run_clicked = st.sidebar.button("🚀 선택한 시나리오 실행 및 벤치마크")

st.divider()

# 레이아웃 2분할 (좌측: US-07 시각화 / 우측: US-08 벤치마크)
col1, col2 = st.columns(2)

# ==========================================
# [US-07] 파티 2분할 공간 시각화 (좌측)
# ==========================================
with col1:
    st.subheader("🕸️ [US-07] 파티 분할 결과 시각화")
    if run_clicked:
        G = nx.Graph()
        G.add_nodes_from(nodes)
        G.add_edges_from(edges)

        pos = nx.spring_layout(G, seed=42)
        fig, ax = plt.subplots(figsize=(5, 4))

        node_colors = ["#ff4b4b" if mock_bitstring[n] == '0' else "#1f77b4" for n in G.nodes()]
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=500, ax=ax)
        nx.draw_networkx_labels(G, pos, font_color="white", font_weight="bold", ax=ax)

        cut_edges = []
        normal_edges = []
        for u, v in G.edges():
            if u < len(mock_bitstring) and v < len(mock_bitstring):
                if mock_bitstring[u] != mock_bitstring[v]:
                    cut_edges.append((u, v))
                else:
                    normal_edges.append((u, v))
            else:
                normal_edges.append((u, v))

        nx.draw_networkx_edges(G, pos, edgelist=normal_edges, edge_color="gray", alpha=0.5, ax=ax)
        nx.draw_networkx_edges(G, pos, edgelist=cut_edges, edge_color="red", style="dashed", width=2.5, ax=ax)

        st.pyplot(fig)
    else:
        st.info("좌측 사이드바에서 시나리오를 고르고 **실행 버튼**을 눌러주세요.")

# ==========================================
# [US-08] 4자 벤치마크 대시보드 UI 연동 (우측)
# ==========================================
with col2:
    st.subheader("📊 [US-08] 알고리즘 4자 성능 비교")
    if run_clicked:
        df = pd.DataFrame(mock_benchmarks)
        
        # 1. 성능 비교 데이터 표 출력
        st.dataframe(df.style.highlight_max(subset=['max_cut_value'], color='lightgreen'), use_container_width=True)
        
        # 2. Max-Cut 밸류 막대그래프 시각화
        fig2, ax2 = plt.subplots(figsize=(5, 3))
        colors = ['#aec7e8', '#ffbb78', '#98df8a', '#ff9896']
        ax2.bar(df["algorithm"], df["max_cut_value"], color=colors)
        ax2.set_ylabel("Max-Cut Value")
        ax2.set_ylim(0, max(df["max_cut_value"]) * 1.2)
        plt.xticks(rotation=15, fontsize=9)
        st.pyplot(fig2)
    else:
        st.info("실행 버튼을 누르면 Brute-Force, SDP, Raw QAOA, Mitigated QAOA 결과가 여기에 표시됩니다.")
=======
# visual/dashboard.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests

def render_comparison_dashboard():
    st.set_page_config(page_title="Max-Cut Dashboard", layout="wide")
    st.title("Max-Cut Algorithm Comparison")
    st.subheader("[T21] 알고리즘 3종 결과 및 실행 시간 비교")

    # API 서버 주소 (방금 터미널에서 켜둔 백엔드)
    API_URL = "http://127.0.0.1:8000/compare"

    # 테스트용 4노드 그래프 데이터
    payload = {
        "matrix": [
            [0.0, 5.0, 2.0, 1.0],
            [5.0, 0.0, 0.0, 3.0],
            [2.0, 0.0, 0.0, 4.0],
            [1.0, 3.0, 4.0, 0.0]
        ],
        "num_nodes": 4,
        "qaoa": {"p": 3, "maxiter": 50, "shots": 1000},
        "sdp": {"rounds": 256, "seed": 0}
    }

    try:
        # 백엔드 API에 진짜 데이터 요청
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        api_data = response.json()
        
        results = api_data.get("results", {})
        
        algos = []
        cut_values = []
        times = []
        
        # 브루트포스, SDP, QAOA 결과 파싱
        for algo_key, run_info in results.items():
            if run_info.get("status") == "success":
                algos.append(algo_key.upper())
                cut_values.append(run_info["result"]["cut_value"])
                times.append(run_info["result"]["runtime_seconds"])
            else:
                algos.append(algo_key.upper() + " (Failed)")
                cut_values.append(0)
                times.append(0)

        df = pd.DataFrame({
            "Algorithm": algos,
            "Max-Cut Value": cut_values,
            "Execution Time (s)": times
        })

    except Exception as e:
        st.error(f"백엔드 API 통신 실패: {e}")
        st.warning("터미널에서 uvicorn 서버가 켜져 있는지 확인해주세요!")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📊 결과 수치 비교표")
        st.dataframe(df, use_container_width=True, hide_index=True)

    with col2:
        st.markdown("### ⏱️ 실행 시간 비교 차트")
        fig, ax = plt.subplots(figsize=(6, 4))
        colors = ['#ff9999', '#66b3ff', '#99ff99']
        
        ax.bar(df["Algorithm"], df["Execution Time (s)"], color=colors)
        ax.set_ylabel("Time (seconds)")
        plt.xticks(rotation=15)
        
        st.pyplot(fig)


if __name__ == "__main__":
    render_comparison_dashboard()
>>>>>>> ab2fdac (feat(core): complete US-03, US-04, US-12 core modules and verify IBM QPU)
