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
| `GET /jobs/{job_id}/download?format=csv` | `200 OK` | 알고리즘 행과 공통 실험 조건·기댓값을 UTF-8 BOM CSV로 내려받는다. |
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
- `result.results`는 `brute_force`, `sdp`, `raw_qaoa`와 M3 분할을 계산하는 경우 `mitigated_qaoa`를 제공한다. 성공한 항목의 `result.bitstring[i]` 또는 `result.assignment[i]`가 노드 `i`의 그룹이다. `approximation_ratio`는 BF 최적 컷 값이 양수일 때 계산한다.
- 표의 컷 값은 선택된 분할에서 계산한다. 기댓값 차트는 `result.qem`에서 값을 읽는다. 값이 `null`이거나 `qem`이 없으면 데이터 없음으로 표시한다. `noisy_sim`은 기존 Raw, M3 및 ZNE를 제공한다. 기존 `details.zne`도 계속 반환한다.
- 일부 알고리즘이 실패하면 Job은 `completed`, `result.status`는 `partial_success`다. 전체 알고리즘 실패 시 Job은 `failed`이며, 생성된 오류 표가 있으면 내려받을 수 있다. 결과가 생성되기 전 다운로드는 `409`, 없는 Job은 `404`, 잘못된 요청은 `422`, 진행 중인 작업만으로 캐시가 차면 `503`이다.

작업 기록은 서버 프로세스의 메모리에 보관한다. 기본값은 동시 실행 2개, 전체 보관 128개, 종료 후 보관 시간 1시간이다. 공간이 필요하면 먼저 종료한 작업부터 제거된다. 재시작하면 기록이 초기화되므로 조회와 다운로드는 작업을 등록한 단일 서버 프로세스에서 처리한다.

## 실제 IBM QPU에서 오류 완화 비교

`POST /jobs`에 다음 요청을 보내면 Raw, M3, ZNE, M3+ZNE를 계산한다.

```json
{
  "matrix": [[0, 2.5], [2.5, 0]],
  "backend": "real_qpu",
  "qaoa": {
    "p": 1,
    "maxiter": 40,
    "shots": 1024,
    "seed": 42,
    "mitigation_method": "both",
    "zne_scales": [1, 3, 5]
  }
}
```

- 같은 장비에서 반복하려면 요청에 `qpu_backend_name`을 지정한다. 생략하면 제출 시 가동 가능한 장비 중 대기 작업이 적은 장비를 선택한다. 실제 사용 장비는 `result.qem.backend_name`에 기록한다.
- 각도 최적화는 Aer에서 수행한다. 최종 회로는 한 번 트랜스파일하고, 물리 회로를 접어 동일한 측정 매핑의 회로를 만든다. 모든 배율은 IBM Runtime Sampler Job 하나로 측정한다. `shots`는 배율별 샷 수다. 위 요청은 총 3,072 QPU 샷을 사용한다. 배율 1 카운트를 Raw와 M3에서 공유하며, M3는 장비가 제공하는 판독 교정값을 사용한다.
- `none`은 Raw만, `m3`는 배율 1의 Raw와 M3를 반환한다. `zne`는 Raw와 ZNE를 반환한다. `both`는 네 지표를 모두 계산한다. `none`과 `zne`에는 대표 M3 분할 행이 없다.
- `result.qem.samples`에는 배율별 원시 카운트, 샷 수, 물리 측정 매핑, 깊이, 2큐비트 게이트 수 및 기댓값이 들어간다. `result.qem.zne_expected_cut`은 원시 기댓값의 선형 외삽 절편이다. `m3_zne_expected_cut`은 같은 배율들의 M3 보정 기댓값을 외삽한 절편이다. 외삽값은 최적 컷 범위로 자르지 않는다. 같은 각도의 무잡음 기준값은 `ideal_expected_cut`이다.
- 폴딩을 준비할 수 없으면 배율 1을 측정하고 `qem.errors`에 사유를 기록한다. M3가 실패하면 사용 가능한 Raw 및 ZNE 지표를 유지한다. 외삽에 필요한 배율이 빠지면 해당 외삽값은 `null`이다. 간선이 없는 그래프는 장비를 호출하지 않는다.

## 개인 IBM 계정으로 제출

대시보드에서 개인 실행 모드를 연결할 때는 `POST /jobs` 본문에 `"backend": "real_qpu"`와 `"qpu_auth": "personal"`을 지정하고 아래 요청 헤더를 제출 시에만 보낸다.

| 헤더 | 값 |
| --- | --- |
| `X-IBM-API-Key` | 사용자가 발급받은 IBM Quantum API 키. 개인 실행 모드에서 필수다. |
| `X-IBM-Instance` | 사용량을 차감할 IBM Quantum 인스턴스의 CRN. 생략하면 IBM SDK가 해당 키로 접근 가능한 인스턴스 중에서 선택한다. |

- 개인 모드에 키가 없거나 헤더 형식이 잘못되면 큐에 등록하지 않고 HTTP 400을 반환한다. `qpu_auth`를 생략한 기존 요청은 키를 보내지 않으면 서버 계정을 사용하고, 키를 보내면 개인 계정을 사용한다. `qpu_auth: "server"`는 개인 헤더와 함께 사용할 수 없다.
- 작업마다 입력한 키로 별도 IBM Runtime 클라이언트를 만들며, 개인 계정 인증이나 장비 접근에 실패해도 서버 계정으로 재시도하지 않는다. 키와 CRN은 작업 응답, CSV·JSON 다운로드 또는 서버 환경 변수에 저장되지 않는다. 공개 배포에서는 HTTPS를 사용하고 프록시·애플리케이션 로그에 인증 헤더를 남기지 않도록 설정한다.
- IBM 인증은 작업이 실행될 때 진행한다. `202 Accepted` 이후 `GET /jobs/{job_id}`의 `quantum_job.job_id`로 IBM 제출 여부를 확인한다. 개인 계정에서 인증 또는 권한 오류가 나면 `result.results.raw_qaoa.error`에서 확인한다.
- 상태 조회와 다운로드에는 IBM 인증 헤더가 필요 없다. 기존 작업 UUID로 조회하므로 대시보드는 이 ID를 작업을 제출한 세션에 보관한다.

## 실행 간 비교와 다운로드

같은 `graph_id`를 기준으로 파일을 모으고, 같은 장비와 측정 매핑인지 확인한 뒤 `p`, `shots` 등의 설정에 따라 비교한다. `graph_id`는 노드 순서와 가중치까지 같은 인접 행렬에 동일하게 부여한다. 각 실행은 `job_id`와 `finished_at`으로 구분한다.

- **CSV**는 기존 분할 결과 열을 유지하고, 각 행에 실험 설정과 Raw·M3·ZNE·M3+ZNE 기댓값을 덧붙인다. 실행당 기댓값을 한 번씩 비교할 때는 `key=raw_qaoa` 행을 사용한다. `shots`는 요청 설정이고 `qpu_shots_used`는 리포트에 기록된 실제 배율별 샷 수의 합이다.
- **JSON**은 조회 응답의 `result`와 동일하다. `request`에 인접 행렬과 전체 설정을 저장하고 `qem.samples`에 배율별 실측 정보를 보존한다. 대시보드에서 기댓값을 비교할 때는 이 응답의 `qem` 필드를 사용한다.

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
