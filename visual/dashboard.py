import json
import time
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx
import requests

# 실행 경로에 관계없이 parser 모듈 안전하게 임포트
try:
    from visual.parser import parse_to_adjacency_matrix
except ImportError:
    from parser import parse_to_adjacency_matrix

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="Q-PartyCut 대시보드", layout="wide")
st.title("Q-PartyCut: 양자 갈등 최적화 시뮬레이터")

# ==========================================
# [US-06 & US-09] 그래프 입력 방식 선택 (프리셋 vs 직접 입력)
# ==========================================
st.sidebar.header("🎯 그래프 데이터 설정 (US-06 / US-09)")
input_mode = st.sidebar.radio(
    "입력 방식 선택",
    ["시나리오 프리셋 (US-09)", "직접 그래프 입력 (US-06 캔버스)"]
)

if input_mode == "시나리오 프리셋 (US-09)":
    preset_choice = st.sidebar.selectbox(
        "대표 갈등 시나리오 선택",
        [
            "시나리오 1: 대립 구도 (N=4)",
            "시나리오 2: 삼각 동맹/갈등 (N=3)",
            "시나리오 3: 다선형 복잡 갈등 (N=5)"
        ]
    )

    if preset_choice == "시나리오 1: 대립 구도 (N=4)":
        nodes = [0, 1, 2, 3]
        weighted_edges = [(0, 1, 1.0), (0, 2, 1.0), (1, 3, 1.0), (2, 3, 1.0)]
    elif preset_choice == "시나리오 2: 삼각 동맹/갈등 (N=3)":
        nodes = [0, 1, 2]
        weighted_edges = [(0, 1, 1.0), (1, 2, 1.0), (2, 0, 1.0)]
    else:  # 시나리오 3: 다선형 복잡 갈등 (N=5)
        nodes = [0, 1, 2, 3, 4]
        weighted_edges = [(0, 1, 1.0), (1, 2, 1.0), (2, 3, 1.0), (3, 4, 1.0), (0, 4, 1.0), (1, 3, 1.0)]

    st.sidebar.info(f"선택된 프리셋: **{preset_choice}**\n- 노드: {len(nodes)}개 / 엣지: {len(weighted_edges)}개")

else:
    # 사용자 직접 그래프(노드·엣지·가중치) 캔버스 입력 UI
    num_custom_nodes = st.sidebar.number_input(
        "노드 개수 (N)", min_value=2, max_value=14, value=4, step=1
    )
    nodes = list(range(int(num_custom_nodes)))

    st.sidebar.caption("아래 표에서 엣지(source, target)와 갈등 가중치(weight)를 직접 추가·수정하세요.")
    default_edges_df = pd.DataFrame([
        {"source": 0, "target": 1, "weight": 2.0},
        {"source": 1, "target": 2, "weight": 1.5},
        {"source": 2, "target": 3, "weight": 2.0},
        {"source": 3, "target": 0, "weight": 1.0},
    ])
    edited_edges_df = st.sidebar.data_editor(
        default_edges_df,
        num_rows="dynamic",
        use_container_width=True,
        key="custom_edge_editor"
    )

    weighted_edges = []
    for _, row in edited_edges_df.iterrows():
        if pd.notna(row["source"]) and pd.notna(row["target"]):
            u, v = int(row["source"]), int(row["target"])
            w = float(row["weight"]) if pd.notna(row["weight"]) else 1.0
            if 0 <= u < len(nodes) and 0 <= v < len(nodes) and u != v:
                weighted_edges.append((u, v, w))

    st.sidebar.info(f"사용자 입력 그래프\n- 노드: {len(nodes)}개 (0~{len(nodes)-1})\n- 유효 엣지: {len(weighted_edges)}개")

# [US-06] parser.py를 호출하여 표준 인접 행렬 JSON으로 파싱
canvas_data = {
    "nodes": [{"id": n} for n in nodes],
    "edges": [{"source": u, "target": v, "weight": w} for u, v, w in weighted_edges]
}
parsed_json_str = parse_to_adjacency_matrix(canvas_data)
parsed_graph_data = json.loads(parsed_json_str)

with st.sidebar.expander("🔍 [US-06] 파싱된 인접 행렬 JSON 보기"):
    st.code(parsed_json_str, language="json")

st.sidebar.divider()

# ==========================================
# [US-12] 노이즈 및 양자 시뮬레이션 파라미터 조절 슬라이더 UI
# ==========================================
st.sidebar.header("🎛️ 시뮬레이션 파라미터 조절 (US-12)")

qaoa_p = st.sidebar.slider(
    "QAOA 회로 깊이 (p)",
    min_value=1, max_value=5, value=2, step=1,
    help="양자 회로의 레이어 깊이입니다."
)

qaoa_shots = st.sidebar.slider(
    "측정 샷 수 (Shots)",
    min_value=256, max_value=4096, value=1024, step=256,
    help="양자 회로 측정 반복 횟수입니다."
)

qaoa_maxiter = st.sidebar.slider(
    "최적화 최대 반복 (Maxiter)",
    min_value=10, max_value=200, value=40, step=10,
    help="고전 옵티마이저의 최대 탐색 횟수입니다."
)

zne_level = st.sidebar.slider(
    "오류 완화(ZNE) 노이즈 스케일 단계",
    min_value=1, max_value=3, value=2, step=1,
    help="1단계: [1, 3] / 2단계: [1, 3, 5] / 3단계: [1, 3, 5, 7]"
)
zne_scales_map = {1: [1, 3], 2: [1, 3, 5], 3: [1, 3, 5, 7]}
selected_zne_scales = zne_scales_map[zne_level]
st.sidebar.caption(f"선택된 ZNE 스케일: `{selected_zne_scales}`")

run_clicked = st.sidebar.button("🚀 시뮬레이션 실행 및 벤치마크", use_container_width=True)

st.divider()

# 레이아웃 2분할 (좌측: US-07 시각화 / 우측: US-08 벤치마크)
col1, col2 = st.columns(2)

with col1:
    st.subheader("🕸️ [US-07] 파티 분할 결과 시각화")
with col2:
    st.subheader("📊 [US-08] 알고리즘 4자 성능 비교")

if run_clicked:
    if len(weighted_edges) == 0:
        st.warning("최소 1개 이상의 유효한 엣지를 입력해 주세요.")
        st.stop()

    # parser.py로 생성된 matrix와 US-12 슬라이더 파라미터 결합
    payload = {
        "num_nodes": parsed_graph_data["num_nodes"],
        "matrix": parsed_graph_data["matrix"],
        "qaoa": {
            "p": qaoa_p,
            "maxiter": qaoa_maxiter,
            "shots": qaoa_shots,
            # 백엔드 benchmark_schemas.py에 zne_scales 반영 시 주석 해제
            # "zne_scales": selected_zne_scales,
        }
    }

    with st.spinner(f"양자 백엔드 시뮬레이션 진행 중... (p={qaoa_p}, shots={qaoa_shots}, ZNE={selected_zne_scales})"):
        try:
            # 비동기 API 호출 및 폴링
            api_url = "http://127.0.0.1:8000/jobs"
            res = requests.post(api_url, json=payload)
            res.raise_for_status()
            job_id = res.json()["job_id"]

            while True:
                status_res = requests.get(f"{api_url}/{job_id}")
                status_data = status_res.json()
                if status_data["status"] in ["completed", "failed"]:
                    break
                time.sleep(2)

            if status_data["status"] == "failed":
                st.error(f"시뮬레이션 작업 실패: {status_data.get('error', '알 수 없는 오류')}")
                st.stop()

            # 실제 결과 데이터 추출
            benchmarks = status_data["result"]["benchmarks"]
            df = pd.DataFrame(benchmarks)
            real_bitstring = status_data["result"]["results"]["mitigated_qaoa"]["result"]["bitstring"]
            
            st.success(f"✅ 시뮬레이션 완료! (비트스트링: `{real_bitstring}` | p={qaoa_p}, shots={qaoa_shots})")
            
            # --- 좌측 렌더링 (실제 비트스트링 및 가중치 반영) ---
            with col1:
                G = nx.Graph()
                G.add_nodes_from(nodes)
                for u, v, w in weighted_edges:
                    G.add_edge(u, v, weight=w)

                pos = nx.spring_layout(G, seed=42)
                fig, ax = plt.subplots(figsize=(5, 4))

                node_colors = ["#ff4b4b" if real_bitstring[n] == '0' else "#1f77b4" for n in G.nodes()]
                nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=500, ax=ax)
                nx.draw_networkx_labels(G, pos, font_color="white", font_weight="bold", ax=ax)

                cut_edges, normal_edges = [], []
                for u, v in G.edges():
                    if real_bitstring[u] != real_bitstring[v]:
                        cut_edges.append((u, v))
                    else:
                        normal_edges.append((u, v))

                nx.draw_networkx_edges(G, pos, edgelist=normal_edges, edge_color="gray", alpha=0.5, ax=ax)
                nx.draw_networkx_edges(G, pos, edgelist=cut_edges, edge_color="red", style="dashed", width=2.5, ax=ax)

                # 가중치가 1.0이 아닌 경우 엣지 라벨 표시
                edge_labels = {(u, v): f"{w:.1f}" for u, v, w in weighted_edges if w != 1.0}
                if edge_labels:
                    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8, ax=ax)

                st.pyplot(fig)

            # --- 우측 렌더링 (실제 벤치마크 차트 반영) ---
            with col2:
                st.dataframe(df.style.highlight_max(subset=['max_cut_value'], color='lightgreen'), use_container_width=True)
                fig2, ax2 = plt.subplots(figsize=(5, 3))
                colors = ['#aec7e8', '#ffbb78', '#98df8a', '#ff9896']
                ax2.bar(df["algorithm"], df["max_cut_value"], color=colors)
                ax2.set_ylabel("Max-Cut Value")
                max_val = df["max_cut_value"].max()
                if pd.notna(max_val) and max_val > 0:
                    ax2.set_ylim(0, max_val * 1.2)
                plt.xticks(rotation=15, fontsize=9)
                st.pyplot(fig2)

        except Exception as e:
            st.error(f"백엔드 연결 실패! 서버가 켜져 있는지 확인하세요. 에러: {e}")
else:
    with col1:
        st.info("좌측 사이드바에서 그래프와 파라미터를 설정하고 **실행 버튼**을 눌러주세요.")
    with col2:
        st.info("실행 버튼을 누르면 알고리즘 4자 성능 비교 결과가 여기에 표시됩니다.")