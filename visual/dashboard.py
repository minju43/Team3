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
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.0]
        ],
        "num_nodes": 4,
        "qaoa": {"p": 1, "maxiter": 50, "shots": 1000},
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