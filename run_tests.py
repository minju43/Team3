import time
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000/jobs"
NUM_TESTS = 20  # 반복 횟수 (1회 요청으로 Raw, M3, ZNE, ZNE+M3 모두 추출)
FALLBACK_MAX_CUT = 14.0

matrix = [
    [0.0, 2.5, 0.0, 0.0, 0.0, 1.5, 2.0, 0.0],
    [2.5, 0.0, 1.5, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 1.5, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.0, 1.5],
    [0.0, 0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 0.0],
    [1.5, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0],
    [2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.5],
    [0.0, 0.0, 0.0, 1.5, 0.0, 0.0, 2.5, 0.0],
]

records = []
print(f"🚀 총 {NUM_TESTS}회 벤치마크 API 호출을 시작합니다 (케이스별 4종 데이터 동시 수집)...\n")

for i in range(NUM_TESTS):
    payload = {
        "num_nodes": 8,
        "matrix": matrix,
        "backend": "noisy_sim",
        "gate_error": 0.01,
        "readout_error": 0.03,
        "qaoa": {
            "p": 2,
            "maxiter": 100,
            "shots": 1024,
            "seed": 42 + i,
            "mitigation_method": "both",
            "zne_scales": [1, 3, 5],
        },
        "sdp": {"seed": 42},
    }

    start_time = time.time()

    try:
        # 1. 작업 등록 (POST /jobs)
        res = requests.post(API_URL, json=payload, timeout=5)
        res.raise_for_status()
        job_id = res.json()["job_id"]

        # 2. 상태 폴링 (GET /jobs/{job_id})
        while True:
            status_res = requests.get(f"{API_URL}/{job_id}", timeout=5)
            status_res.raise_for_status()
            status_data = status_res.json()
            if status_data.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.8)

        total_elapsed = time.time() - start_time

        if status_data.get("status") != "completed":
            print(f"  - [{i+1}/{NUM_TESTS}] 백엔드 연산 실패: {status_data.get('error')}")
            continue

        result_body = status_data.get("result") or {}
        optimal_cut = result_body.get("optimal_cut_value") or FALLBACK_MAX_CUT
        results_dict = result_body.get("results") or {}

        raw_res = (results_dict.get("raw_qaoa") or {}).get("result") or {}
        mit_res = (results_dict.get("mitigated_qaoa") or {}).get("result") or {}
        zne_info = (mit_res.get("details") or {}).get("zne") or {}

        # 3. 4가지 케이스별 컷 값 및 소요 시간 추출
        raw_cut = float(raw_res.get("cut_value", 0.0))
        m3_cut = float(mit_res.get("cut_value", 0.0))
        zne_cut = float(zne_info.get("expected_cut_value", m3_cut))
        both_cut = max(m3_cut, zne_cut)

        raw_time = float(raw_res.get("runtime_seconds", total_elapsed))
        m3_time = float(mit_res.get("runtime_seconds", total_elapsed))
        # benchmark.py에서 ZNE는 mitigated_qaoa의 runtime_seconds 이후에 별도 실행됨
        zne_time = max(total_elapsed, m3_time)
        both_time = round(zne_time + max(0.0, m3_time - raw_time), 2)

        def to_acc(cut_val: float) -> float:
            return round(min(max(cut_val / optimal_cut, 0.0), 1.0), 4)

        batch = [
            {"Test_ID": i + 1, "Method": "Raw (None)", "Accuracy": to_acc(raw_cut),  "Time_sec": round(raw_time, 2),  "Cost_USD": 5.0},
            {"Test_ID": i + 1, "Method": "M3 Only",    "Accuracy": to_acc(m3_cut),   "Time_sec": round(m3_time, 2),   "Cost_USD": 6.5},
            {"Test_ID": i + 1, "Method": "ZNE Only",   "Accuracy": to_acc(zne_cut),  "Time_sec": round(zne_time, 2),  "Cost_USD": 15.0},
            {"Test_ID": i + 1, "Method": "ZNE + M3",   "Accuracy": to_acc(both_cut), "Time_sec": both_time,           "Cost_USD": 16.5},
        ]
        records.extend(batch)

        print(
            f"  - [{i+1}/{NUM_TESTS}] 완료 ({total_elapsed:.1f}s) | "
            f"Raw: {to_acc(raw_cut):.3f} | M3: {to_acc(m3_cut):.3f} | "
            f"ZNE: {to_acc(zne_cut):.3f} | Both: {to_acc(both_cut):.3f}"
        )

    except Exception as e:
        print(f"  - [{i+1}/{NUM_TESTS}] API 통신 에러: {e}")

# 4. 데이터가 있을 때만 CSV 저장 (빈 파일 덮어쓰기 방지)
if not records:
    print("\n❌ 수집된 데이터가 없습니다. 백엔드 서버가 켜져 있는지 확인하세요.")
else:
    df = pd.DataFrame(records)
    df.to_csv("quantum_experiment_logs.csv", index=False)
    print(f"\n✅ 총 {len(records)}건 저장 완료! ('quantum_experiment_logs.csv')")