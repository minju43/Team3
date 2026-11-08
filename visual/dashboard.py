# visual/dashboard.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

def render_comparison_dashboard():
    st.set_page_config(page_title="Max-Cut Dashboard", layout="wide")
    st.title("Max-Cut Algorithm Comparison")
    st.subheader("[T21] 알고리즘 3종 결과 및 실행 시간 비교")

    # T21: 가상의 알고리즘 실행 결과 데이터 (이후 백엔드 T19 API 결과와 연동됨)
    data = {
        "Algorithm": ["Brute-Force (BF)", "Goemans-Williamson (SDP)", "QAOA (Quantum)"],
        "Max-Cut Value": [4.5, 4.0, 4.2],
        "Execution Time (s)": [0.05, 0.12, 1.5]
    }
    df = pd.DataFrame(data)

    col1, col2 = st.columns(2)

    # 왼쪽 단: 결과 수치 비교표
    with col1:
        st.markdown("### 📊 결과 수치 비교표")
        st.dataframe(df, use_container_width=True, hide_index=True)

    # 오른쪽 단: 실행 시간 비교 바 차트
    with col2:
        st.markdown("### ⏱️ 실행 시간 비교 차트")
        fig, ax = plt.subplots(figsize=(6, 4))
        colors = ['#ff9999', '#66b3ff', '#99ff99']
        
        ax.bar(df["Algorithm"], df["Execution Time (s)"], color=colors)
        ax.set_ylabel("Time (seconds)")
        plt.xticks(rotation=15)
        
        # 차트를 Streamlit 화면에 렌더링
        st.pyplot(fig)

if __name__ == "__main__":
    render_comparison_dashboard()