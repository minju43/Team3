"""Streamlit 서버에서 벤치마크 API를 호출한다."""
import os
from uuid import UUID

import requests
from pydantic import ValidationError

from api.benchmark_schemas import JobResponse


# API가 응답했으면 HTTP 상태 코드가 담긴다. 연결 실패·응답 형식 오류에서는 None이다.
class JobAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _request(method: str, path: str, **kwargs) -> requests.Response:
    # 이 주소는 브라우저가 아닌 Streamlit 서버에서 접근할 수 있어야 한다.
    # FastAPI가 별도 호스트나 포트에서 실행되면 Streamlit 프로세스의 환경 변수로 지정한다.
    base_url = os.getenv("QPARTYCUT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        # timeout 튜플의 단위는 초이며 순서대로 연결, 응답 읽기 제한이다.
        response = requests.request(method, f"{base_url}{path}", timeout=(3, 5), **kwargs)
    except requests.RequestException as exc:
        raise JobAPIError("백엔드에 연결할 수 없습니다.") from exc

    if response.ok:
        return response

    # FastAPI의 일반 오류 detail은 문자열이고, 422 검증 오류는 메시지 목록이다.
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, list):
        detail = " / ".join(
            error["msg"] for error in detail if isinstance(error, dict) and isinstance(error.get("msg"), str)
        )
    if not isinstance(detail, str):
        detail = None
    raise JobAPIError(detail or f"백엔드 요청에 실패했습니다 (HTTP {response.status_code}).",
                      status_code=response.status_code)


def _read_job(response: requests.Response) -> tuple[JobResponse, int]:
    # 공통 API 스키마로 검증해 job.job_id, job.status, job.result를 속성으로 읽을 수 있게 한다.
    try:
        job = JobResponse.model_validate_json(response.content)
    except ValidationError as exc:
        raise JobAPIError("백엔드가 올바른 작업 상태를 반환하지 않았습니다.") from exc
    # 반환값의 두 번째 항목은 다음 조회까지 기다릴 시간(초)이다.
    retry_after = response.headers.get("Retry-After", "2")
    return job, max(2, int(retry_after)) if retry_after.isascii() and retry_after.isdecimal() else 2


# 실행 버튼을 누를 때 한 번 호출한다. 반환된 job.job_id를 세션에 저장한다.
def submit_job(payload: dict) -> tuple[JobResponse, int]:
    return _read_job(_request("POST", "/jobs", json=payload))


# queued/running이면 반환된 간격을 사용해 다시 조회한다.
# completed/failed에 도달하면 조회를 중단하고 job.result와 job.error를 확인한다.
def read_job(job_id: UUID) -> tuple[JobResponse, int]:
    return _read_job(_request("GET", f"/jobs/{job_id}"))


# job.result가 있으면 "csv" 또는 "json"을 요청하고, 반환된 바이트를 다운로드 버튼에 전달한다.
# 파일명과 MIME 타입은 호출 화면에서 형식에 맞춰 지정한다.
def download_job(job_id: UUID, file_format: str) -> bytes:
    return _request("GET", f"/jobs/{job_id}/download", params={"format": file_format}).content
