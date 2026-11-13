"""API 실행 계층에서 사용하는 결과 검증 오류를 정의한다."""


class AlgorithmExecutionError(RuntimeError):
    """알고리즘 출력이 공통 결과 계약이나 최적값 범위를 위반한 경우."""
