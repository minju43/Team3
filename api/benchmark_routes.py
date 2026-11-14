"""비동기 실행 등록, 상태 조회와 벤치마크 결과 다운로드 API."""
import csv
from io import StringIO
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from .benchmark_schemas import BenchmarkRequest, BenchmarkRow, JobResponse
from .jobs import JobQueue, JobQueueFull

router = APIRouter(prefix="/jobs", tags=["Sprint 2 벤치마크"])
queue = JobQueue()


def _get_job(job_id: UUID) -> JobResponse:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없거나 보관 기간이 끝났습니다.")
    return job


@router.post("", status_code=202, response_model=JobResponse, summary="4종 벤치마크 등록")
def submit_job(payload: BenchmarkRequest, request: Request, response: Response) -> JobResponse:
    try:
        job = queue.submit(payload)
    except JobQueueFull:
        raise HTTPException(status_code=503, detail="작업 큐가 가득 찼습니다.", headers={"Retry-After": "2"}) from None
    response.headers["Location"] = request.url_for("get_job", job_id=job.job_id).path
    response.headers["Retry-After"] = "2"
    return job


@router.get("/{job_id}", response_model=JobResponse, summary="벤치마크 작업 상태 및 결과 조회")
def get_job(job_id: UUID, response: Response) -> JobResponse:
    response.headers["Cache-Control"] = "no-store"
    job = _get_job(job_id)
    if job.status in {"queued", "running"}:
        response.headers["Retry-After"] = "2"
    return job


@router.get("/{job_id}/download", response_class=Response, summary="벤치마크 CSV 또는 JSON 다운로드",
            responses={200: {"content": {"application/json": {}, "text/csv": {}}}})
def download_job(job_id: UUID, format: Literal["csv", "json"] = "json") -> Response:
    job = _get_job(job_id)
    if job.result is None:
        headers = {"Retry-After": "2"} if job.status in {"queued", "running"} else None
        raise HTTPException(status_code=409, detail="다운로드할 벤치마크 결과가 없습니다.", headers=headers)

    headers = {"Content-Disposition": f'attachment; filename="benchmark-{job_id}.{format}"',
               "Cache-Control": "no-store"}
    if format == "json":
        return Response(job.result.model_dump_json(), media_type="application/json", headers=headers)

    # UTF-8 BOM을 붙여 Excel에서도 한글 오류 메시지를 읽을 수 있게 한다.
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(BenchmarkRow.model_fields))
    writer.writeheader()
    writer.writerows(row.model_dump() for row in job.result.benchmarks)
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv", headers=headers)
