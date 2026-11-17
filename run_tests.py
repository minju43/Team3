import requests
import time
import pandas as pd

API_URL = "http://127.0.0.1:8000/jobs"
NUM_TESTS = 20  # 각 케이스별 반복 횟수
MAX_CUT_EXACT = 14.0  # N=8 기본 갈등망 프리셋 기준 이론적 최대 컷 값

# 프론트엔드 대시보드의 N=8 기본 파티 갈등망 (2.5, 1.5 등 완벽 일치)
matrix = [
    [0.0, 2.5, 0.0, 0.0, 0.0, 1.5, 2.0, 0.0],
    [2.5, 0.0, 1.5, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 1.5, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.0, 1.5],
    [0.0, 0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 0.0],
    [1.5, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0],
    [2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.5],
    [0.0, 0.0, 0.0, 1.5, 0.0, 0.0, 2.5, 0.0]
]

# 수정된 schemas.py의 mitigation_method("none", "m3", "zne", "both")를 정확히 호출
test_cases = [
    {"method": "Raw (None)", "cost": 5.0,  "mitigation": "none"},
    {"method": "M3 Only",    "cost": 6.5,  "mitigation": "m3"},
    {"method": "ZNE Only",   "cost": 15.0, "mitigation": "zne"},
    {"method": "ZNE + M3",   "cost": 16.5, "mitigation": "both"}
]

records = []

print(f"🚀 총 {len(test_cases) * NUM_TESTS}회의 양자 엔진 자동화 테스트를 시작합니다...\n")

for case in test_cases:
    print(f"▶ 현재 테스트 케이스: {case['method']}")
    
    for i in range(NUM_TESTS):
        # 방금 수정한 schemas.py 규격에 완벽히 맞춘 페이로드
        payload = {
            "num_nodes": 8,
            "matrix": matrix,
            "qaoa": {
                "p": 2,
                "shots": 1024,
                "seed": 42 + i,  # 궤적이 조금씩 달라지도록 시드값 미세 변동
                "mitigation_method": case["mitigation"],
                "zne_scales": [1, 3, 5]
            },
            "sdp": {"seed": 42}
        }
        
        start_time = time.time()
        
        try:
            # 1. API 호출 (작업 생성)
            res = requests.post(API_URL, json=payload, timeout=5)
            res.raise_for_status()
            job_id = res.json().get("job_id")
            
            # 2. Polling (완료 대기)
            while True:
                status_res = requests.get(f"{API_URL}/{job_id}", timeout=5)
                status_data = status_res.json()
                if status_data.get("status") in ["completed", "failed"]:
                    break
                time.sleep(0.8)
                
            elapsed_time = time.time() - start_time
            
            # 3. 결과 파싱 및 로깅
            if status_data.get("status") == "completed":
                results_dict = status_data.get("result", {}).get("results", {})
                
                # 백엔드의 응답 키(mitigated_qaoa 또는 raw_qaoa, qaoa 등)를 유연하게 획득
                qaoa_result = results_dict.get("mitigated_qaoa") or results_dict.get("raw_qaoa") or results_dict.get("qaoa", {})
                real_cut_value = qaoa_result.get("result", {}).get("cut_value", 0.0)
                accuracy = min(real_cut_value / MAX_CUT_EXACT, 1.0)
                
                print(f"  - [{i+1}/{NUM_TESTS}] 완료 | 소요시간: {elapsed_time:.1f}초 | 정확도: {accuracy:.3f}")
                
                records.append({
                    "Test_ID": i + 1,
                    "Method": case["method"],
                    "Accuracy": accuracy,
                    "Time_sec": round(elapsed_time, 2),
                    "Cost_USD": case["cost"]
                })
            else:
                print(f"  - [{i+1}/{NUM_TESTS}] 백엔드 연산 실패 (Failed)")
                
        except Exception as e:
            print(f"  - [{i+1}/{NUM_TESTS}] API 통신 에러: {e}")

df = pd.DataFrame(records)
df.to_csv("quantum_experiment_logs.csv", index=False)
print("\n✅ 모든 테스트 완료! 'quantum_experiment_logs.csv' 파일이 저장되었습니다.")