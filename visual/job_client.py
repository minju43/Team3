"""Streamlit 서버에서 벤치마크 API를 호출한다."""
import os
from uuid import UUID

import requests
from pydantic import ValidationError

from api.benchmark_schemas import JobResponse


class JobAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _request(method: str, path: str, **kwargs) -> requests.Response:
    base_url = os.getenv("QPARTYCUT_API_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        response = requests.request(method, f"{base_url}{path}", timeout=(3, 5), **kwargs)
    except requests.RequestException as exc:
        raise JobAPIError("백엔드에 연결할 수 없습니다.") from exc

    if response.ok:
        return response

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
    raise JobAPIError(detail or f"백엔드 요청이 실패했습니다 (HTTP {response.status_code}).",
                      status_code=response.status_code)


def _read_job(response: requests.Response) -> tuple[JobResponse, int]:
    try:
        job = JobResponse.model_validate_json(response.content)
    except ValidationError as exc:
        raise JobAPIError("백엔드가 올바른 작업 상태를 반환하지 않았습니다.") from exc
    retry_after = response.headers.get("Retry-After", "2")
    return job, max(2, int(retry_after)) if retry_after.isascii() and retry_after.isdecimal() else 2


def submit_job(payload: dict, headers: dict[str, str] | None = None) -> tuple[JobResponse, int]:
    return _read_job(_request("POST", "/jobs", json=payload, headers=headers))


def read_job(job_id: UUID) -> tuple[JobResponse, int]:
    return _read_job(_request("GET", f"/jobs/{job_id}"))


def download_job(job_id: UUID, file_format: str) -> bytes:
    return _request("GET", f"/jobs/{job_id}/download", params={"format": file_format}).content