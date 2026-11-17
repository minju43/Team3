"""고전 알고리즘 두 종과 완화 전후 QAOA를 같은 그래프에서 비교한다."""
import logging
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from time import perf_counter, sleep
from typing import Any, Callable

import numpy as np

from .benchmark_schemas import BENCHMARK_LABELS, BenchmarkRequest, BenchmarkResponse, BenchmarkRow, QuantumJob
from .errors import AlgorithmExecutionError
from .mapping import sampled_partition_result
from .pipeline import _collect_comparison, _run_brute_force, _run_sdp

logger = logging.getLogger(__name__)


@dataclass
class _Measurement:
    """완화 전후에 공유하는 샷과 ZNE 계산에 필요한 최적 회로."""

    counts: dict[str, int]
    measured_circuit: Any
    bound_circuit: Any
    backend: Any
    operator: Any
    offset: float
    details: dict
    elapsed: float


# 11/18 수정 · 측정 함수에서 시드를 받아 Aer 샘플링에 적용함.
def _run_quantum_job(circuit, backend, mode, shots, report_job, *, seed=None):
    """측정 작업의 제공자 상태를 백그라운드에서 조회하고 원시 카운트를 반환한다."""
    if mode == "real_qpu":
        # IBM QPU는 ISA 회로를 Runtime Sampler에 제출한다.
        from qiskit_ibm_runtime import SamplerV2

        job = SamplerV2(mode=backend).run([circuit], shots=shots)
    else:
        job = backend.run(circuit, shots=shots, seed_simulator=seed)

    job_id = job.job_id()
    while True:
        state = job.status()
        status = getattr(state, "name", state)
        report_job(QuantumJob(job_id=job_id, backend_name=backend.name, status=status.lower()))
        if status in {"DONE", "ERROR", "CANCELLED"}:
            break
        if status not in {"INITIALIZING", "VALIDATING", "QUEUED", "RUNNING"}:
            raise AlgorithmExecutionError("양자 백엔드가 알 수 없는 작업 상태를 반환했습니다.")
        sleep(2 if mode == "real_qpu" else 0.05)

    result = job.result()
    return result[0].data.meas.get_counts() if mode == "real_qpu" else result.get_counts()


def _mitigate_counts(counts, circuit, backend, mode, readout_error):
    """같은 측정 카운트에 장비 또는 노이즈 모델의 판독 보정 행렬을 적용한다."""
    import mthree
    from mthree.utils import final_measurement_mapping

    mapping = final_measurement_mapping(circuit)
    if mode == "real_qpu":
        properties = backend.properties()
        calibrations = [None] * backend.num_qubits
        for qubit in mapping.values():
            p10, _ = properties.qubit_property(qubit, "prob_meas1_prep0")
            p01, _ = properties.qubit_property(qubit, "prob_meas0_prep1")
            calibrations[qubit] = [[1 - p10, p01], [p10, 1 - p01]]
    else:
        error = readout_error if mode == "noisy_sim" else 0.0
        calibrations = [None] * circuit.num_qubits
        for qubit in mapping.values():
            calibrations[qubit] = [[1 - error, error], [error, 1 - error]]

    mitigator = mthree.M3Mitigation()
    mitigator.cals_from_matrices([None if matrix is None else np.asarray(matrix, dtype=np.float32)
                                 for matrix in calibrations])
    # M3의 음수 준확률을 보존하고, 가장 높은 준확률의 분할을 선택한다.
    return {bits: float(value) for bits, value in mitigator.apply_correction(counts, mapping).items()}


def _sample_result(matrix, distribution, elapsed, details):
    """Qiskit 비트 순서를 노드 순서로 바꾸고 실제 분할의 컷 값을 계산한다."""
    if not distribution or not all(isfinite(value) for value in distribution.values()):
        raise AlgorithmExecutionError("QAOA 측정 분포가 비어 있거나 유한하지 않습니다.")
    bitstring = max(distribution, key=distribution.get)[::-1]
    groups = [[node for node, bit in enumerate(bitstring) if bit == group] for group in "01"]
    return sampled_partition_result(
        matrix, (bitstring, *groups, distribution), runtime_seconds=elapsed,
        details={**details, "distribution": distribution},
    )


def run_benchmark(request: BenchmarkRequest, report_job: Callable[[QuantumJob], None]) -> BenchmarkResponse:
    """공통 최적화와 샘플링을 한 번 수행하고 완화 전후의 분할을 독립적으로 기록한다."""
    matrix = request.to_adjacency_matrix()
    inputs = request.to_solver_inputs()
    mode = request.backend
    # 11/18 수정 · 요청에서 변환한 샷 수와 시드를 측정 및 ZNE에서 공통으로 사용함.
    shots = inputs["qaoa_sampler"]["shots"]
    seed = inputs["qaoa_sampler"]["seed"]

    @lru_cache(maxsize=1)
    def measure():
        """원시 샷을 두 결과가 공유하며, 실패한 양자 작업을 재제출하지 않는다."""
        start = perf_counter()
        try:
            from qiskit import transpile
            from core.backend_manager import QuantumBackendManager
            from core.hamiltonian import build_maxcut_pauli_list
            from core.optimizer import optimize_qaoa_parameters
            from core.qaoa_circuit import bind_qaoa_parameters, build_qaoa_circuit

            operator, offset = build_maxcut_pauli_list(matrix)
            circuit, gamma_vec, beta_vec = build_qaoa_circuit(**inputs["qaoa_circuit"])
            # 실제 장비에는 최적화 반복마다 제출하는 대신 Aer에서 구한 각도로 측정한다.
            gamma, beta, energy, _ = optimize_qaoa_parameters(
                circuit, operator, **inputs["qaoa_optimizer"], shots=shots,
                mode="noisy_sim" if mode == "noisy_sim" else "ideal",
                gate_error=request.gate_error, readout_error=request.readout_error,
            )
            # 기존 최적화기는 이름순으로 각도를 반환하므로 벡터의 레이어 순서로 다시 매핑한다.
            gamma_by_param = dict(zip(sorted(gamma_vec, key=lambda param: param.name), gamma))
            beta_by_param = dict(zip(sorted(beta_vec, key=lambda param: param.name), beta))
            bound = bind_qaoa_parameters(circuit, gamma_vec, beta_vec,
                                         [gamma_by_param[param] for param in gamma_vec],
                                         [beta_by_param[param] for param in beta_vec])
            manager = QuantumBackendManager()
            if mode == "real_qpu":
                backend = manager.connect_ibm_service().least_busy(
                    operational=True, simulator=False, min_num_qubits=len(matrix),
                )
            else:
                backend = manager.get_backend(mode, request.gate_error, request.readout_error)
            # 11/18 수정 · 회로 변환과 측정에 시드를 전달하고 비교 결과에 깊이, 샷 수, 시드를 기록함.
            measured = transpile(bound.measure_all(inplace=False), backend, seed_transpiler=seed)
            counts = _run_quantum_job(measured, backend, mode, shots, report_job, seed=seed)
            details = {
                "backend": backend.name, "p": inputs["qaoa_circuit"]["p"], "shots": shots, "seed": seed,
                "optimizer_expected_cut_value": float(energy + offset),
            }
            if not isfinite(details["optimizer_expected_cut_value"]):
                raise AlgorithmExecutionError("QAOA 최적화 기댓값이 유한하지 않습니다.")
            return _Measurement(counts, measured, bound, backend, operator, offset,
                                details, perf_counter() - start), None
        except Exception as exc:
            return None, exc

    def qaoa_result(*, mitigated):
        if not any(weight for row in matrix for weight in row):
            return _sample_result(matrix, {"0" * len(matrix): 1.0}, 0.0, {"skipped": True})

        measurement, error = measure()
        if error is not None:
            raise error
        counts = measurement.counts
        details = measurement.details
        elapsed = measurement.elapsed
        start = perf_counter()
        total = sum(counts.values())
        if total <= 0:
            raise AlgorithmExecutionError("QAOA 측정 카운트가 비어 있습니다.")
        if mitigated:
            distribution = _mitigate_counts(counts, measurement.measured_circuit, measurement.backend,
                                            mode, request.readout_error)
            elapsed += perf_counter() - start
            details = {**details, "mitigation": "m3", "distribution_type": "quasi_probability"}
            # ZNE는 노이즈 시뮬레이터의 기댓값 지표로 제공하며, M3 분할 및 표의 시간은 그대로 사용한다.
            if mode == "noisy_sim":
                try:
                    from core.mitigation import run_zne_estimator

                    # 11/18 수정 · 요청의 ZNE 배율, 샷 수, 시드를 외삽 계산에 전달함.
                    zne = run_zne_estimator(measurement.bound_circuit, measurement.operator,
                                            scale_factors=inputs["mitigation"]["zne_scales"],
                                            gate_error=request.gate_error, readout_error=request.readout_error,
                                            shots=shots, seed=seed)
                    expected_cut = zne["zne_richardson_energy"] + measurement.offset
                    if not all(isfinite(value) for value in [expected_cut, *zne["noisy_energies"],
                                                            zne["raw_noisy_energy"], zne["zne_linear_energy"]]):
                        raise AlgorithmExecutionError("ZNE 추정값이 유한하지 않습니다.")
                    details["zne"] = {**zne, "expected_cut_value": expected_cut}
                except Exception:
                    logger.exception("ZNE 기댓값 계산 실패")
                    details["zne_error"] = "ZNE 기댓값을 계산하지 못했습니다."
        else:
            distribution = {bits: count / total for bits, count in counts.items()}
            elapsed += perf_counter() - start
            details = {**details, "distribution_type": "probability"}
        return _sample_result(matrix, distribution, elapsed, details)

    comparison = _collect_comparison(matrix, inputs, (
        ("brute_force", _run_brute_force), ("sdp", _run_sdp),
        ("raw_qaoa", lambda _matrix, _inputs: qaoa_result(mitigated=False)),
        ("mitigated_qaoa", lambda _matrix, _inputs: qaoa_result(mitigated=True)),
    ))
    rows = []
    for key, run in comparison.results.items():
        ratio = comparison.approximation_ratios[key]
        rows.append(BenchmarkRow(
            key=key, algorithm=BENCHMARK_LABELS[key], status=run.status,
            max_cut_value=run.result.cut_value if run.result else None,
            time=run.result.runtime_seconds if run.result else None,
            bitstring=run.result.bitstring if run.result else None,
            approximation_ratio=ratio.value, approximation_ratio_reason=ratio.reason,
            error_code=run.error.code if run.error else None, error_message=run.error.message if run.error else None,
        ))
    return BenchmarkResponse(**comparison.model_dump(), backend=mode, benchmarks=rows)
