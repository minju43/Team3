import time
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000/jobs"
OUTPUT_CSV = "hyperparameter_sweep_logs.csv"
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

def run_one(backend: str, p: int, shots: int, zne_scales: list[int]):
    payload = {
        "num_nodes": 8,
        "matrix": matrix,
        "backend": backend,
        "gate_error": 0.004,
        "readout_error": 0.02,
        "qaoa": {
            "p": p,
            "maxiter": 100,
            "shots": shots,
            "seed": 42,
            "mitigation_method": "both",
            "zne_scales": zne_scales,
        },
        "sdp": {"seed": 42},
    }

    t0 = time.time()
    res = requests.post(API_URL, json=payload, timeout=5)
    res.raise_for_status()
    job_id = res.json()["job_id"]

    while True:
        st_res = requests.get(f"{API_URL}/{job_id}", timeout=5)
        st_res.raise_for_status()
        data = st_res.json()
        if data.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.5)

    elapsed = round(time.time() - t0, 2)
    if data.get("status") != "completed":
        raise RuntimeError(data.get("error"))

    body = data.get("result") or {}
    opt = float(body.get("optimal_cut_value") or FALLBACK_MAX_CUT)
    qem = body.get("qem") or {}

    def ratio(val):
        return round(min(max(float(val) / opt, 0.0), 1.0), 4) if val is not None else None

    return {
        "backend": backend,
        "p": p,
        "shots": shots,
        "zne_scales": str(zne_scales),
        "raw_acc": ratio(qem.get("raw_expected_cut")),
        "m3_acc": ratio(qem.get("m3_expected_cut")),
        "zne_acc": ratio(qem.get("zne_expected_cut")),
        "m3_zne_acc": ratio(qem.get("m3_zne_expected_cut")),
        "elapsed_sec": elapsed,
    }

tasks = []
# 1) 히트맵 & [1, 3] 기준선 (p=1~4 x shots=256~4096)
for p in [1, 2, 3, 4]:
    for shots in [256, 512, 1024, 2048, 4096]:
        tasks.append(("noisy_sim", p, shots, [1, 3]))

# 2) ZNE 배율 간격 [1, 3, 5] 비교 (2048샷 고정)
for p in [1, 2, 3, 4]:
    tasks.append(("noisy_sim", p, 2048, [1, 3, 5]))

# 3) 무잡음(Ideal) 이론 상한 비교 (2048샷 고정)
for p in [1, 2, 3, 4]:
    tasks.append(("ideal", p, 2048, [1, 3]))

records = []
print(f"🚀 총 {len(tasks)}개 하이퍼파라미터 조합 실측을 시작합니다...\n")

for idx, (backend, p, shots, scales) in enumerate(tasks, 1):
    try:
        row = run_one(backend, p, shots, scales)
        records.append(row)
        print(
            f"[{idx:02d}/{len(tasks)}] {backend:9s} | p={p} | {shots:4d}샷 | {str(scales):9s} -> "
            f"Raw={row['raw_acc']} | ZNE+M3={row['m3_zne_acc']} ({row['elapsed_sec']}s)"
        )
    except Exception as e:
        print(f"[{idx:02d}/{len(tasks)}] 실패 ({backend}, p={p}, shots={shots}): {e}")

if records:
    pd.DataFrame(records).to_csv(OUTPUT_CSV, index=False)
    print(f"\n✅ 실측 저장 완료: {OUTPUT_CSV} ({len(records)}건)")