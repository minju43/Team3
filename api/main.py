"""동기 비교와 비동기 벤치마크를 제공하는 FastAPI 진입점."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .benchmark_routes import router as benchmark_router
from .pipeline import compare_algorithms
from .schemas import ComparisonResponse, MaxCutRequest

# 서버 실행: .venv/Scripts/python.exe -m uvicorn api.main:app --reload
# 11/15 수정 · API 설명을 갱신하고 비동기 벤치마크 Job 라우터를 등록함.
app = FastAPI(title="Q-PartyCut 백엔드", description="Max-Cut 비교 및 비동기 벤치마크 API")
app.include_router(benchmark_router)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(request: Request, exc: RequestValidationError):
    """잘못된 요청을 422로 반환하며 NaN 입력이나 예외 객체의 직렬화 실패를 피한다."""
    errors = [{"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
              for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.post("/compare", response_model=ComparisonResponse, summary="알고리즘 3종 실행 및 비교")
def compare(request: MaxCutRequest) -> ComparisonResponse:
    """요청을 검증한 뒤 세 알고리즘 결과와 BF 기준 근사비를 반환한다.

    CPU 계산은 동기 엔드포인트의 작업 스레드에서 실행한다.
    실행 실패는 응답의 개별 오류로, 잘못된 요청은 HTTP 422로 구분한다.
    """
    return compare_algorithms(request)
