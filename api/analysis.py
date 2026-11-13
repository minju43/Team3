"""BF의 정확한 최적 컷 값을 기준으로 알고리즘별 관측 근사비를 계산한다."""
from .schemas import AlgorithmRun, ApproximationRatio


def analyze_approximation_ratios(results: dict[str, AlgorithmRun]):
    """근사비와 계산 불가 사유를 반환하며, 영으로 나누거나 추정값을 기준으로 쓰지 않는다.

    반환되는 값은 이번 실행의 관측 비율이며 SDP의 이론적 기대 보장과는 구별된다.
    """
    baseline = results.get("brute_force")
    optimum = (baseline.result.cut_value if baseline and baseline.status == "success"
               and baseline.result is not None else None)
    ratios = {}
    for name, run in results.items():
        # 알고리즘 실패와 기준값 부재를 각각 명시하여 부분 성공도 해석할 수 있게 한다.
        if run.status != "success" or run.result is None:
            ratios[name] = ApproximationRatio(reason="알고리즘 실행에 실패했습니다.")
        elif optimum is None:
            ratios[name] = ApproximationRatio(reason="BF 최적값을 구하지 못해 근사비를 계산할 수 없습니다.")
        elif optimum == 0:
            ratios[name] = ApproximationRatio(reason="최적 컷 값이 0이므로 0/0 비율은 정의되지 않습니다.")
        else:
            ratios[name] = ApproximationRatio(value=run.result.cut_value / optimum)
    return optimum, ratios
