# 백엔드 구조와 알고리즘 실행 API

## 파일별 역할

| 파일 | 역할 |
| --- | --- |
| `api/schemas.py` | 입력 DTO, 행렬·옵션 검증, 함수별 인자 매핑, 응답 스키마 |
| `api/main.py` | FastAPI 진입점, HTTP 요청 검증 오류 처리 |
| `api/pipeline.py` | BF·SDP·QAOA 실행, 개별 실패 격리, 결과 통합 |
| `api/mapping.py` | 고전 결과와 QAOA 샘플러 출력을 API 공통 결과로 변환 |
| `api/analysis.py` | BF 최적값 기준 관측 근사비 분석 |
| `api/errors.py` | 결과 계약 위반을 나타내는 실행 예외 |
| `classical/brute_force.py` | BF 정확해 계산 |
| `classical/sdp_cut.py` | Goemans-Williamson SDP 및 무작위 라운딩 |
| `classical/common.py` | 검증기를 호출하는 계산용 배열 변환, 컷 계산, 결과 자료형 |
| `core/validator.py` | 기존 노드 수·대칭성·자기 루프·음수 가중치 검증 (원본 유지) |
| `core/` | 기존 QAOA 회로·해밀토니안·최적화·샘플링 구현 |

QAOA 전용 `sampled_partition_result()`는 `classical`에서 제거하고 `api/mapping.py`로 옮겼다.
고전 결과의 `to_partition_tuple()`도 제거했으며 API 응답이 공통 비교 형식을 제공한다.
BF·SDP의 수학적 계산식과 QAOA 구현은 유지한다.
중복된 `classical.common.validate_adjacency_matrix()`는 제거했으며,
`prepare_adjacency_matrix()`가 `core.validator.validate_adjacency_matrix()`를 호출한 뒤
독립된 NumPy float64 배열을 반환한다. `core/validator.py`는 원본을 유지한다.
기존 코어의 리스트 입력에 맞추는 변환과 예외 연결은 `prepare_adjacency_matrix()`가 담당한다.
이 변환 함수에서 불리언·유한하지 않은 가중치·전체 합의 오버플로를 추가로 거절한다.
코어의 `GraphValidationError`는 수정하지 않고 호출부에서 `ValueError`로 연결하므로
Pydantic이 API 입력 검증 오류로 처리할 수 있다.

## 서버 실행과 요청

프로젝트 루트에서 Python 3.10 가상환경을 사용한다.

```powershell
.venv/Scripts/python.exe -m uvicorn api.main:app --reload
```

`POST /compare`에 다음 JSON을 전달한다. 대화형 API 문서는 `/docs`에서 확인한다.

```json
{
  "matrix": [[0, 5], [5, 0]],
  "num_nodes": 2,
  "qaoa": {"p": 1, "maxiter": 100, "shots": 1024},
  "sdp": {"rounds": 256, "seed": 0}
}
```

`data/presets.json`의 시나리오 객체도 입력으로 쓸 수 있다.
`name`, `description`, `num_nodes`는 선택 필드이며 생략된 노드 수는 계산한다.
입력은 2~14개 노드의 대칭 정사각 행렬, 비음수 유한 숫자 가중치,
0 대각선을 요구한다. 대칭 위치의 값은 공통 코어 기준에 따라 정확히 같아야 한다.
이전에 고전 검증기에서 허용하던 1e-10 이내의 대칭 오차 보정은 적용하지 않는다.
문자열·불리언 가중치, 알 수 없는 필드, 잘못된 실행 옵션은 거절한다.
QAOA 코어는 시드를 지원하지 않으므로 QAOA 요청 옵션에도 노출하지 않는다.

## 실행과 응답

BF를 먼저 실행하고 SDP와 QAOA를 이어서 실행한다.
각 알고리즘을 독립적으로 예외 처리하므로 하나가 실패해도 나머지를 실행한다.
서버 내부에서 직접 호출하려면 다음을 사용한다.

```python
from api.schemas import MaxCutRequest
from api.pipeline import compare_algorithms

request = MaxCutRequest(matrix=[[0, 5], [5, 0]])
response = compare_algorithms(request)
print(response.model_dump_json())
```

| 응답 필드 | 의미 |
| --- | --- |
| `status` | `success`, `partial_success`, `error` 중 전체 실행 상태 |
| `results` | `brute_force`, `sdp`, `qaoa`별 성공 결과 또는 오류 |
| `optimal_cut_value` | BF 성공 시 정확한 최적값, BF 실패 시 null |
| `approximation_ratios` | 알고리즘별 관측 근사비 또는 계산 불가 사유 |

성공 결과에는 `algorithm`, `assignment`, `partition`, `bitstring`, `cut_value`,
`runtime_seconds`, `details`가 들어간다. 노드 i의 그룹은 `assignment[i]`이며,
비트스트링도 0번 노드부터 순서대로 기록한다.
BF의 평가 횟수, SDP 솔버 상태와 완화 목적값, QAOA 각도·에너지 이력 등은
`details`에 저장한다. QAOA 시간은 회로 생성부터 최적화와 샘플링까지 포함한다.

## 근사비와 예외 처리

관측 근사비는 `실제 분할의 컷 값 / BF 최적 컷 값`이다.
BF 자신은 양의 최적값에 대해 1이다. QAOA 에너지 기댓값이나 SDP 완화 목적값을
실제 컷 값이나 정확한 기준값 대신 사용하지 않는다.
SDP의 이론적 기대 근사비 보장과 이번 실행에서 관측된 비율은 다르다.

- BF 실패: 모든 비율을 null로 두며 기준값을 구하지 못한 사유를 제공한다.
- 알고리즘 실패: 해당 결과의 비율을 null로 두고 실행 오류를 제공한다.
- BF 최적값이 0: 0/0은 정의되지 않으므로 비율은 null이고 사유를 제공한다.
- 간선이 없는 그래프: QAOA 실행을 생략하고 컷 값 0의 분할을 반환한다.
- 컷 값이 BF 최적값을 초과: 정상 비율로 보정하지 않고 해당 결과를 오류 처리한다.
- 잘못된 HTTP 입력: HTTP 422와 필드별 검증 오류를 반환한다.
- 알고리즘 실행 오류: HTTP 200의 개별 결과에 `error.code`, `error.message`를 담는다.
  전체 성공 여부는 응답의 `status`로 판단한다.

오류 코드는 `dependency_unavailable`, `invalid_result`, `invalid_algorithm_input`,
`execution_failed`로 구분하며 내부 오류 상세는 서버 로그에 기록한다.

## 기존 코어의 동작과 한계

현재 `core/sampler.py`는 Aer가 아닌 `qiskit.primitives.Sampler`를 사용한다.
최대 컷을 가진 관측 상태가 아니라 최빈 상태를 선택하며, 네 번째 반환값은
실제 정수 측정 횟수가 아닌 준확률 분포이다. API는 이 동작을 유지하고
샘플러 종류와 선택 정책을 QAOA `details`에 명시한다.
QAOA 측정 결과와 실행 시간은 실행마다 달라질 수 있다.
현재 코어의 Estimator/Sampler V1에서는 deprecated 경고가 발생한다.

## 검증

```powershell
.venv/Scripts/python.exe -B -m pytest tests/ -q
```

DTO 검증, 프리셋 입력, 계산 기저의 해밀토니안-컷 일치, 노드 순서,
세 알고리즘 실제 실행, 개별·전체 실패, 영행렬, 잘못된 최적값 초과 결과,
HTTP 성공 응답과 422 검증 오류를 포함한다.
이벤트 루프용 로컬 소켓을 만들 수 없는 격리 환경에서는 HTTP 검증 4개를
건너뛰고 사유를 표시한다. 그 경우 실제 HTTP 요청 처리는 별도 환경에서 확인해야 한다.
