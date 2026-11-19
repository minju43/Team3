"""비동기 실행 등록, 상태 조회와 벤치마크 결과 다운로드 API."""
import csv
import json
import logging
from io import StringIO
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import SecretStr

from .benchmark_schemas import BenchmarkRequest, BenchmarkRow, JobResponse
from .jobs import JobQueue, JobQueueFull
from .qpu_credentials import PersonalQpuCredentials

router = APIRouter(prefix="/jobs", tags=["Sprint 2 벤치마크"])
queue = JobQueue()
logger = logging.getLogger("uvicorn.error").getChild(__name__)


def _get_job(job_id: UUID) -> JobResponse:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없거나 보관 기간이 끝났습니다.")
    return job


@router.post("", status_code=202, response_model=JobResponse, summary="4종 벤치마크 등록")
def submit_job(
    payload: BenchmarkRequest, request: Request, response: Response,
    ibm_api_key: Annotated[str | None, Header(alias="X-IBM-API-Key")] = None,
    ibm_instance: Annotated[str | None, Header(alias="X-IBM-Instance")] = None,
) -> JobResponse:
    credentials = _personal_qpu_credentials(payload, request, ibm_api_key, ibm_instance)
    try:
        job = queue.submit(payload, credentials=credentials)
    except JobQueueFull:
        logger.warning("벤치마크 큐 포화 backend=%s nodes=%s", payload.backend, payload.num_nodes)
        raise HTTPException(status_code=503, detail="작업 큐가 가득 찼습니다.", headers={"Retry-After": "2"}) from None
    except RuntimeError:
        logger.exception("벤치마크 작업을 등록하지 못했습니다.")
        raise HTTPException(status_code=503, detail="현재 벤치마크 작업을 등록할 수 없습니다.",
                            headers={"Retry-After": "2"}) from None
    response.headers["Location"] = request.url_for("get_job", job_id=job.job_id).path
    response.headers["Retry-After"] = "2"
    response.headers["Cache-Control"] = "no-store"
    return job


def _personal_qpu_credentials(
    payload: BenchmarkRequest, request: Request, api_key: str | None, instance: str | None,
) -> PersonalQpuCredentials | None:
    # 헤더 값을 검증 오류 본문이나 벤치마크 요청 모델에 넣지 않는다.
    if any(len(request.headers.getlist(name)) > 1 for name in ("X-IBM-API-Key", "X-IBM-Instance")):
        raise HTTPException(status_code=400, detail="IBM 자격 증명 헤더는 각각 한 번만 지정하세요.")
    if api_key is None and payload.qpu_auth != "personal" and instance is None:
        return None
    if payload.backend != "real_qpu" or payload.qpu_auth == "server":
        raise HTTPException(status_code=400, detail="개인 IBM 자격 증명은 개인 real_qpu 실행에만 사용하세요.")
    if not api_key or any(not 33 <= ord(char) <= 126 or char == "," for char in api_key):
        raise HTTPException(status_code=400, detail="유효한 형식의 X-IBM-API-Key 헤더가 필요합니다.")
    if instance is not None and (not instance.startswith("crn:") or
                                 any(not 33 <= ord(char) <= 126 or char == "," for char in instance)):
        raise HTTPException(status_code=400, detail="X-IBM-Instance 헤더에는 IBM 인스턴스 CRN을 지정하세요.")
    return PersonalQpuCredentials(SecretStr(api_key), instance)


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
        detail = ("벤치마크 작업이 진행 중입니다." if headers
                  else "작업에서 다운로드할 벤치마크 결과를 생성하지 못했습니다.")
        raise HTTPException(status_code=409, detail=detail, headers=headers)

    headers = {"Content-Disposition": f'attachment; filename="benchmark-{job_id}.{format}"',
               "Cache-Control": "no-store"}
    logger.info("벤치마크 다운로드 job_id=%s format=%s", job_id, format)
    if format == "json":
        return Response(job.result.model_dump_json(), media_type="application/json", headers=headers)

    # UTF-8 BOM을 붙여 Excel에서도 한글 오류 메시지를 읽을 수 있게 한다.
    output = StringIO(newline="")
    result = job.result
    config = result.request
    qem = result.qem
    experiment = {
        "job_id": str(job.job_id),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "graph_id": result.graph_id,
        "num_nodes": result.num_nodes,
        "backend": result.backend,
        "backend_name": qem.backend_name if qem else None,
        "provider_job_id": qem.provider_job_id if qem else None,
        "p": config.qaoa.p if config else None,
        "shots": config.qaoa.shots if config else None,
        "maxiter": config.qaoa.maxiter if config else None,
        "qaoa_seed": config.qaoa.seed if config else None,
        "sdp_rounds": config.sdp.rounds if config else None,
        "sdp_seed": config.sdp.seed if config else None,
        "gate_error": config.gate_error if config and result.backend == "noisy_sim" else None,
        "readout_error": config.readout_error if config and result.backend == "noisy_sim" else None,
        "mitigation_method": config.qaoa.mitigation_method if config else None,
        "zne_scales": json.dumps(config.qaoa.zne_scales) if config else None,
        "qpu_shots_used": sum(sample.shots for sample in qem.samples) if qem and qem.samples else None,
        "optimal_cut_value": result.optimal_cut_value,
        "extrapolator": qem.extrapolator if qem else None,
        "ideal_expected_cut": qem.ideal_expected_cut if qem else None,
        "raw_expected_cut": qem.raw_expected_cut if qem else None,
        "m3_expected_cut": qem.m3_expected_cut if qem else None,
        "zne_expected_cut": qem.zne_expected_cut if qem else None,
        "m3_zne_expected_cut": qem.m3_zne_expected_cut if qem else None,
        "qem_errors": json.dumps(qem.errors, ensure_ascii=False) if qem and qem.errors else None,
    }
    writer = csv.DictWriter(output, fieldnames=[*BenchmarkRow.model_fields, *experiment])
    writer.writeheader()
    writer.writerows({**row.model_dump(), **experiment} for row in result.benchmarks)
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv", headers=headers)
