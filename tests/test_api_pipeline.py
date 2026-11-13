"""실제 파이프라인 실행, 관측 근사비, 개별 실패 격리와 HTTP 응답을 검증한다."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from functools import lru_cache

import pytest

# 기존 테스트와 같이 프로젝트 모듈을 직접 불러올 수 있도록 경로를 추가한다.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from api import pipeline
from api.main import app
from api.schemas import MaxCutRequest


# pytest와 파일 직접 실행에서 동일한 테스트 입력을 사용한다.
FAILURE_CASES = [("_run_sdp", "sdp"), ("_run_qaoa", "qaoa")]

INVALID_HTTP_INPUTS = [
    {"matrix": [[0, 1], [2, 0]]},
    {"matrix": [[0, float("nan")], [float("nan"), 0]]},
    {"matrix": [[0, 1], [1, 0]], "qaoa": {"shots": -1}},
]


def _request(matrix=None):
    """작은 그래프와 짧은 실행 옵션으로 통합 검증용 요청을 만든다."""
    return MaxCutRequest(matrix=matrix if matrix is not None else [[0, 5], [5, 0]],
                         qaoa={"maxiter": 40, "shots": 128})


def test_pipeline_real_three_algorithms():
    """세 알고리즘을 실제로 실행하고 정확한 컷 값, 비율, JSON 응답을 확인한다."""
    response = pipeline.compare_algorithms(_request())
    assert response.status == "success"
    assert response.optimal_cut_value == 5
    assert set(response.results) == {"brute_force", "sdp", "qaoa"}
    for name, run in response.results.items():
        assert run.status == "success"
        assert run.result.cut_value == 5
        assert run.result.runtime_seconds >= 0
        assert response.approximation_ratios[name].value == 1
    assert "quasi_distribution" in response.results["qaoa"].result.details
    json.loads(response.model_dump_json())


def test_zero_optimum_is_undefined():
    """영행렬은 코어 바인딩 없이 처리하고 0/0을 임의의 비율로 만들지 않는다."""
    response = pipeline.compare_algorithms(_request([[0, 0], [0, 0]]))
    assert response.status == "success"
    assert response.optimal_cut_value == 0
    assert response.results["qaoa"].result.details["skipped"]
    for ratio in response.approximation_ratios.values():
        assert ratio.value is None
        assert "0/0" in ratio.reason


def _failure(matrix, inputs):
    """실행 중 예외를 재현하며 내부 경로가 응답에 노출되지 않는지도 확인한다."""
    raise RuntimeError("비공개 경로와 내부 오류 정보")


@pytest.mark.parametrize("runner,name", FAILURE_CASES)
def test_one_failure_does_not_drop_other_results(monkeypatch, runner, name):
    """한 알고리즘의 실패가 다른 알고리즘과 근사비 계산을 중단하지 않아야 한다."""
    monkeypatch.setattr(pipeline, runner, _failure)
    response = pipeline.compare_algorithms(_request([[0, 0], [0, 0]]))
    assert response.status == "partial_success"
    assert response.results[name].error.code == "execution_failed"
    assert "비공개" not in response.model_dump_json()
    assert response.approximation_ratios[name].value is None
    assert sum(run.status == "success" for run in response.results.values()) == 2


def test_bf_failure_removes_ratio_baseline(monkeypatch):
    """BF가 실패하면 SDP 완화값 등을 대체 기준으로 사용하지 않는다."""
    monkeypatch.setattr(pipeline, "_run_brute_force", _failure)
    response = pipeline.compare_algorithms(_request([[0, 0], [0, 0]]))
    assert response.status == "partial_success"
    assert response.optimal_cut_value is None
    assert all(ratio.value is None for ratio in response.approximation_ratios.values())
    assert "BF" in response.approximation_ratios["sdp"].reason


def test_all_failed(monkeypatch):
    """모든 알고리즘이 실패해도 구조화된 전체 실패 응답을 반환한다."""
    for runner in ("_run_brute_force", "_run_sdp", "_run_qaoa"):
        monkeypatch.setattr(pipeline, runner, _failure)
    response = pipeline.compare_algorithms(_request())
    assert response.status == "error"
    assert response.optimal_cut_value is None


def test_reject_result_above_exact_optimum(monkeypatch):
    """BF 최적값을 초과하는 잘못된 솔버 결과를 정상 근사비로 보고하지 않는다."""
    def invalid_result(matrix, inputs):
        result = pipeline._run_brute_force(matrix, inputs)
        return result.model_copy(update={"cut_value": result.cut_value + 1})
    monkeypatch.setattr(pipeline, "_run_sdp", invalid_result)
    response = pipeline.compare_algorithms(_request([[0, 0], [0, 0]]))
    assert response.status == "partial_success"
    assert response.results["sdp"].error.code == "invalid_result"


@lru_cache(maxsize=1)
def _check_event_loop_available():
    """격리 환경에서 이벤트 루프의 로컬 소켓 생성이 차단되는지 제한 시간 내 확인한다."""
    try:
        check = subprocess.run(
            [sys.executable, "-B", "-c",
             "import socket, asyncio; socket.setdefaulttimeout(1); asyncio.run(asyncio.sleep(0))"],
            capture_output=True, timeout=3,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("현재 격리 환경에서는 이벤트 루프용 로컬 소켓을 생성할 수 없습니다.")
    if check.returncode:
        pytest.skip("현재 격리 환경에서는 이벤트 루프용 로컬 소켓을 생성할 수 없습니다.")


def _post(payload):
    """별도 HTTP 클라이언트 패키지 없이 ASGI를 통해 실제 요청 처리를 검증한다."""
    _check_event_loop_available()

    async def invoke():
        messages = []
        body = json.dumps(payload).encode()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/compare", "raw_path": b"/compare",
                 "query_string": b"", "headers": [(b"content-type", b"application/json")],
                 "server": ("test", 80), "client": ("test", 1234), "root_path": ""}

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        return status, json.loads(content)
    return asyncio.run(invoke())


def test_http_compare_success():
    """FastAPI가 요청을 DTO로 검증하고 공통 응답을 HTTP 200으로 반환하는지 확인한다."""
    status, body = _post(_request([[0, 0], [0, 0]]).model_dump())
    assert status == 200
    assert body["status"] == "success"
    assert len(body["results"]) == 3


@pytest.mark.parametrize("payload", INVALID_HTTP_INPUTS)
def test_http_invalid_input_is_422(payload):
    """잘못된 입력과 NaN을 안전하게 직렬화한 HTTP 422 오류로 반환한다."""
    status, body = _post(payload)
    assert status == 422
    assert body["detail"]


if __name__ == "__main__":
    print("=== API 실행 파이프라인 검증 시작 ===")
    cases = [
        ("세 알고리즘 실행 및 근사비", test_pipeline_real_three_algorithms, (), False),
        ("최적값 0 처리", test_zero_optimum_is_undefined, (), False),
        ("BF 실패 시 기준값 제거", test_bf_failure_removes_ratio_baseline, (), True),
        ("모든 알고리즘 실패 처리", test_all_failed, (), True),
        ("BF 최적값 초과 결과 거절", test_reject_result_above_exact_optimum, (), True),
        ("HTTP 정상 응답", test_http_compare_success, (), False),
    ]
    cases += [(f"{name} 실패 격리", test_one_failure_does_not_drop_other_results, (runner, name), True)
              for runner, name in FAILURE_CASES]
    cases += [(f"HTTP 잘못된 입력 거절 {i}", test_http_invalid_input_is_422, (payload,), False)
              for i, payload in enumerate(INVALID_HTTP_INPUTS, 1)]
    passed = failed = skipped = 0
    for label, test, args, needs_patch in cases:
        try:
            # 예외 재현용 함수 교체는 각 항목 종료 시 자동으로 원복한다.
            with pytest.MonkeyPatch.context() as monkeypatch:
                if needs_patch:
                    # 의도적으로 만든 오류의 서버 로그가 실제 테스트 실패처럼 보이지 않게 한다.
                    monkeypatch.setattr(pipeline.logger, "disabled", True)
                    test(monkeypatch, *args)
                else:
                    test(*args)
        except pytest.skip.Exception as exc:
            skipped += 1
            print(f"[건너뜀] {label}: {exc}")
        except (Exception, pytest.fail.Exception) as exc:
            failed += 1
            print(f"[실패] {label}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[성공] {label}")
    print(f"\nAPI 파이프라인 결과: 성공 {passed}개 / 실패 {failed}개 / 건너뜀 {skipped}개")
    if skipped:
        print("건너뛴 항목은 검증되지 않았습니다. 위의 사유를 확인하세요.")
    raise SystemExit(1 if failed else 0)
