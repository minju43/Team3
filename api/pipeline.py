"""QAOA·BF·SDP를 실행하고 출력 변환, 근사비 분석, 개별 예외 처리를 조정한다."""
import logging
from time import perf_counter

import numpy as np

from .analysis import analyze_approximation_ratios
from .errors import AlgorithmExecutionError
from .mapping import classical_result_to_api, sampled_partition_result
from .schemas import AlgorithmError, AlgorithmRun, ComparisonResponse, MaxCutRequest

logger = logging.getLogger(__name__)


def _run_brute_force(matrix, inputs):
    """정확한 기준값을 구하고 고전 결과를 API 결과로 변환한다."""
    from classical.brute_force import brute_force_max_cut
    return classical_result_to_api(matrix, brute_force_max_cut(**inputs["brute_force"]))


def _run_sdp(matrix, inputs):
    """SDP 근사 알고리즘을 실행하고 솔버 상태 등 부가 정보를 보존한다."""
    from classical.sdp_cut import goemans_williamson_max_cut
    return classical_result_to_api(matrix, goemans_williamson_max_cut(**inputs["sdp"]))


def _run_qaoa(matrix, inputs):
    """기존 코어의 회로 생성·최적화·샘플링을 연결하고 전체 시간을 측정한다."""
    start = perf_counter()
    # 간선이 없으면 모든 분할의 컷 값이 0이다. 미사용 gamma 바인딩 오류도 피한다.
    if not np.any(matrix):
        sample = ("0" * len(matrix), list(range(len(matrix))), [], {})
        return sampled_partition_result(matrix, sample, runtime_seconds=perf_counter() - start,
                                        details={"skipped": True, "reason": "간선이 없는 그래프입니다."})

    # 양자 의존성은 실행 시 불러와 설치 오류가 BF·SDP까지 중단시키지 않도록 한다.
    from core.hamiltonian import build_maxcut_pauli_list
    from core.qaoa_circuit import build_qaoa_circuit
    from core.optimizer import optimize_qaoa_parameters
    from core.sampler import get_best_partition

    operator, offset = build_maxcut_pauli_list(matrix)
    circuit, gamma_vec, beta_vec = build_qaoa_circuit(**inputs["qaoa_circuit"])
    gamma, beta, energy, history = optimize_qaoa_parameters(
        circuit, operator, **inputs["qaoa_optimizer"])
    sample = get_best_partition(circuit, gamma_vec, beta_vec, gamma, beta,
                                **inputs["qaoa_sampler"])
    # 실제 컷 값과 기댓값을 구별하고 준확률 분포를 JSON 키로 변환한다.
    details = {
        "gamma": list(map(float, gamma)), "beta": list(map(float, beta)),
        "expected_cut_value": float(energy + offset),
        "energy_history": list(map(float, history)), "offset": float(offset),
        "shots": inputs["qaoa_sampler"]["shots"],
        "selection_policy": "most_frequent", "sampler": "qiskit.primitives.Sampler",
        "quasi_distribution": {str(key): float(value) for key, value in sample[3].items()},
    }
    if not all(np.isfinite(value) for value in
               [*details["gamma"], *details["beta"], details["expected_cut_value"],
                *details["energy_history"], *details["quasi_distribution"].values()]):
        raise AlgorithmExecutionError("QAOA가 유한하지 않은 수치 결과를 반환했습니다.")
    return sampled_partition_result(matrix, sample, runtime_seconds=perf_counter() - start,
                                    details=details)


def compare_algorithms(request: MaxCutRequest) -> ComparisonResponse:
    """세 알고리즘을 순차 실행하고, 한 종류가 실패해도 나머지 결과를 반환한다."""
    matrix = request.to_adjacency_matrix()
    inputs = request.to_solver_inputs()
    results = {}
    # BF를 먼저 실행하여 다른 알고리즘의 컷 값이 최적값을 넘는지도 검사한다.
    for name, runner in (("brute_force", _run_brute_force), ("sdp", _run_sdp), ("qaoa", _run_qaoa)):
        try:
            result = runner(matrix, inputs)
            baseline = results.get("brute_force")
            if baseline and baseline.result and result.cut_value > baseline.result.cut_value:
                raise AlgorithmExecutionError("계산한 컷 값이 BF 최적값을 초과했습니다.")
            # JSON으로 직렬화할 수 없는 부가 정보 역시 해당 알고리즘의 실패로 처리한다.
            result.model_dump_json()
            results[name] = AlgorithmRun(status="success", result=result)
        except Exception as exc:
            # 오류 상세는 서버 로그에 기록하고 응답에는 경로·스택 추적을 노출하지 않는다.
            logger.exception("알고리즘 실행 실패: %s", name)
            if isinstance(exc, ImportError):
                code, message = "dependency_unavailable", "알고리즘 실행에 필요한 패키지를 불러오지 못했습니다."
            elif isinstance(exc, AlgorithmExecutionError):
                code, message = "invalid_result", str(exc)
            elif isinstance(exc, ValueError):
                code, message = "invalid_algorithm_input", "알고리즘 입력 또는 실행 옵션을 처리하지 못했습니다."
            else:
                code, message = "execution_failed", "알고리즘 실행 중 오류가 발생했습니다. 서버 로그를 확인하세요."
            results[name] = AlgorithmRun(status="error", error=AlgorithmError(code=code, message=message))

    # 실패한 알고리즘의 근사비는 비워 두고 전체 실행 상태를 구분한다.
    optimum, ratios = analyze_approximation_ratios(results)
    successes = sum(run.status == "success" for run in results.values())
    status = "success" if successes == 3 else "partial_success" if successes else "error"
    return ComparisonResponse(status=status, num_nodes=len(matrix), results=results,
                              optimal_cut_value=optimum, approximation_ratios=ratios)
