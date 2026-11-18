# Sprint 2 벤치마크 API

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload
.\.venv\Scripts\python.exe -m pytest tests/test_sprint2_benchmark.py -v
```

FastAPI 요청·응답 스키마는 서버의 `/docs`에서 확인할 수 있다. Sprint 1의 `POST /compare`도 계속 사용할 수 있다.

| 요청 | 정상 응답 | 프론트 사용 방법 |
| --- | --- | --- |
| `POST /jobs` | `202 Accepted` | 응답 본문의 `job_id`를 저장하고 `Location` 경로를 조회한다. |
| `GET /jobs/{job_id}` | `200 OK` | `queued` 또는 `running`이면 `Retry-After`에 따라 다시 조회한다. `completed` 또는 `failed`면 조회를 끝낸다. |
| `GET /jobs/{job_id}/download?format=csv` | `200 OK` | `result.benchmarks`의 네 행을 UTF-8 BOM CSV로 내려받는다. |
| `GET /jobs/{job_id}/download?format=json` | `200 OK` | 조회 응답의 `result` 객체를 JSON 파일로 내려받는다. |

## 요청 형식

예시는 캔버스 파서의 출력을 사용한다. 프리셋은 `adjacency_matrix` 대신 `matrix`를 그대로 보낸다. `qaoa`와 `sdp` 실행 옵션은 Sprint 1과 동일하다.

```json
{
  "num_nodes": 2,
  "adjacency_matrix": [[0, 2.5], [2.5, 0]],
  "backend": "noisy_sim",
  "qaoa": {"p": 1, "maxiter": 40, "shots": 1024}
}
```

`backend`는 `noisy_sim`(기본값), `ideal`, `real_qpu`를 지원한다. `noisy_sim`의 기본 게이트 오류율은 `0.01`, 판독 오류율은 `0.03`이며 각각 `gate_error`, `readout_error`로 지정한다. `real_qpu`는 서버의 IBM 자격증명을 사용한다. `quantum_job`에는 측정 작업이 제출된 뒤 제공자의 Job ID, 기기 이름과 최근 상태가 표시된다. 최상위 `status`는 고전 알고리즘과 후처리까지 포함한 벤치마크 전체의 상태다.

## 표와 그래프 연동

- `result.benchmarks`의 `algorithm`, `max_cut_value`, `time`을 대시보드 표에 사용한다. `time`의 단위는 초다. `status: error`인 행에는 `error_message`가 들어가며, 컷 값과 실행 시간은 `null`이다. 그래프를 그릴 때는 컷 값이 있는 행을 사용한다.
- `result.results`의 키는 `brute_force`, `sdp`, `raw_qaoa`, `mitigated_qaoa`다. 성공한 항목의 `result.bitstring[i]` 또는 `result.assignment[i]`가 노드 `i`의 그룹이다. `approximation_ratio`는 BF 최적 컷 값이 양수일 때 계산한다.
- Raw QAOA와 M3는 같은 샷을 사용한다. 두 방식의 `time`은 공통 최적화, 샘플링 대기 및 각 후처리 시간을 포함한다. `noisy_sim`의 ZNE는 `result.results.mitigated_qaoa.result.details.zne`에 기댓값으로 제공한다. 표의 컷 값은 선택된 분할에서 계산하며, 표의 시간에는 별도 ZNE 지표 계산 시간이 포함되지 않는다.
- 일부 알고리즘이 실패하면 Job은 `completed`, `result.status`는 `partial_success`다. 전체 알고리즘 실패 시 Job은 `failed`이며, 생성된 오류 표가 있으면 내려받을 수 있다. 결과가 생성되기 전 다운로드는 `409`, 없는 Job은 `404`, 잘못된 요청은 `422`, 진행 중인 작업만으로 캐시가 차면 `503`이다.

작업 기록은 서버 프로세스의 메모리에 보관한다. 기본값은 동시 실행 2개, 전체 보관 128개, 종료 후 보관 시간 1시간이다. 공간이 필요하면 먼저 종료한 작업부터 제거된다. 재시작하면 기록이 초기화되므로 조회와 다운로드는 작업을 등록한 단일 서버 프로세스에서 처리한다.

## API 실행 및 검증

대시보드 연동 시 `visual/job_client.py`를 사용할 수 있다. `submit_job()`의 응답에서 `job_id`를 저장하고, `read_job()`으로 상태를 조회한다. 작업 결과가 있으면 `download_job()`에서 받은 바이트를 CSV 또는 JSON 다운로드 버튼에 전달한다. FastAPI 주소가 기본값 `http://127.0.0.1:8000`과 다르면 Streamlit을 실행하는 환경에서 `QPARTYCUT_API_URL`을 지정한다.

Python 3.10 가상 환경을 활성화한 상태에서 의존성과 소스를 점검한다.

```powershell
python -m pip install -r requirements.txt
python -m pip check
python -m compileall -q api classical core
python -m pytest tests -q
```

프로젝트 루트에서 API를 단일 워커로 실행한다.

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

API의 `/healthz`가 `{"status":"ok"}`를 반환하는지 확인한다. `/docs`에서 위 예시를 `POST /jobs`로 제출한 뒤 `GET /jobs/{job_id}`에서 상태와 네 알고리즘 결과를 확인한다. 결과가 생성되면 다운로드 엔드포인트에 `format=csv`와 `format=json`을 각각 요청한다. 행렬의 행·열 크기와 노드 수가 2~14 범위를 벗어나면 HTTP 422가 반환된다. Uvicorn 로그에서 같은 Job ID로 등록, 실행, 양자 작업 상태 변경, 종료 및 다운로드를 추적할 수 있다.
