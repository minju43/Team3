"""고전 알고리즘 두 종과 완화 전후 QAOA를 같은 그래프에서 비교한다."""
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from math import isfinite
from time import perf_counter, sleep
from typing import Any, Callable

import numpy as np

from .benchmark_schemas import (BENCHMARK_LABELS, BenchmarkRequest, BenchmarkResponse, BenchmarkRow,
                                QEMReport, QEMSample, QuantumJob)
from .errors import AlgorithmExecutionError
from .mapping import sampled_partition_result
from .pipeline import _collect_comparison, _run_brute_force, _run_sdp
from .qpu_credentials import PersonalQpuCredentials
from .qpu_mitigation import build_folded_measurements, expected_cut, extrapolate_linear

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
    folded_samples: dict[int, tuple[Any, dict[str, int]]] = field(default_factory=dict)
    provider_job_id: str | None = None
    folding_failed: bool = False


# 11/18 수정 · 측정 함수에서 시드를 받아 Aer 샘플링에 적용함.
def _run_quantum_job(circuit, backend, mode, shots, report_job, *, seed=None):
    """측정 작업의 제공자 상태를 백그라운드에서 조회하고 원시 카운트를 반환한다."""
    if mode == "real_qpu":
        results, _ = _run_qpu_job([circuit], backend, shots, report_job)
        return results[0]
    job = backend.run(circuit, shots=shots, seed_simulator=seed)
    return _wait_quantum_job(job, backend, report_job, poll_seconds=0.05).get_counts()


def _run_qpu_job(circuits, backend, shots, report_job):
    from qiskit_ibm_runtime import SamplerV2

    # 같은 요청의 배율들을 한 Runtime Job에 넣어 큐 대기와 실행 시점 차이를 줄인다.
    job = SamplerV2(mode=backend).run(circuits, shots=shots)
    results = _wait_quantum_job(job, backend, report_job, poll_seconds=2)
    counts = [pub.data.meas.get_counts() for pub in results]
    if len(counts) != len(circuits):
        raise AlgorithmExecutionError("IBM 측정 결과 수와 제출한 회로 수가 일치하지 않습니다.")
    return counts, job.job_id()


def _wait_quantum_job(job, backend, report_job, *, poll_seconds):
    job_id = job.job_id()
    while True:
        state = job.status()
        status = getattr(state, "name", state)
        report_job(QuantumJob(job_id=job_id, backend_name=backend.name, status=status.lower()))
        if status in {"DONE", "ERROR", "CANCELLED"}:
            break
        if status not in {"INITIALIZING", "VALIDATING", "QUEUED", "RUNNING"}:
            raise AlgorithmExecutionError("양자 백엔드가 알 수 없는 작업 상태를 반환했습니다.")
        sleep(poll_seconds)

    return job.result()


def _mitigate_counts(counts, circuit, backend, mode, readout_error, *, properties=None):
    """같은 측정 카운트에 장비 또는 노이즈 모델의 판독 보정 행렬을 적용한다."""
    import mthree
    from mthree.utils import final_measurement_mapping

    mapping = final_measurement_mapping(circuit)
    if mode == "real_qpu":
        if properties is None:
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


def _qpu_mitigation_report(matrix, measurement, request):
    """같은 배율별 카운트에서 네 가지 지표를 구하고 배율 1의 M3 분포를 재사용한다."""
    from qiskit.quantum_info import Statevector

    method = request.qaoa.mitigation_method
    report = QEMReport(backend_name=measurement.backend.name, provider_job_id=measurement.provider_job_id)
    if measurement.folding_failed:
        report.errors["folding"] = "장비용 폴딩 회로를 준비하지 못해 배율 1만 측정했습니다."
    try:
        energy = Statevector.from_instruction(measurement.bound_circuit).expectation_value(measurement.operator)
        report.ideal_expected_cut = float(energy.real + measurement.offset)
    except Exception:
        logger.exception("무잡음 기준 기댓값 계산 실패")
        report.errors["ideal"] = "무잡음 기준 기댓값을 계산하지 못했습니다."

    properties = None
    if method in {"m3", "both"}:
        try:
            properties = measurement.backend.properties()
            if properties is None:
                raise AlgorithmExecutionError("장비 판독 교정 정보가 없습니다.")
        except Exception as exc:
            logger.warning("장비 판독 교정 정보 조회 실패: %s", type(exc).__name__)
            report.errors["m3"] = "장비 판독 교정 정보를 가져오지 못했습니다."

    base_corrected = None
    samples = {1: (measurement.measured_circuit, measurement.counts), **measurement.folded_samples}
    for scale, (circuit, counts) in samples.items():
        shots = sum(counts.values())
        if shots <= 0:
            report.errors[f"raw_scale_{scale}"] = "이 배율에서 유효한 측정 카운트를 받지 못했습니다."
            continue
        try:
            point = QEMSample(
                scale=scale, shots=shots, depth=circuit.depth(),
                two_qubit_gates=sum(len(item.qubits) == 2 and item.operation.name != "barrier"
                                    for item in circuit.data),
                measurement_mapping={
                    circuit.find_bit(item.clbits[0]).index: circuit.find_bit(item.qubits[0]).index
                    for item in circuit.data if item.operation.name == "measure"
                },
                counts=counts,
                raw_expected_cut=expected_cut(matrix, {bits: count / shots for bits, count in counts.items()}),
            )
        except (AlgorithmExecutionError, ValueError):
            logger.exception("측정 카운트 처리 실패: scale=%s", scale)
            report.errors[f"raw_scale_{scale}"] = "이 배율의 측정 카운트를 처리하지 못했습니다."
            continue
        if properties is not None:
            try:
                corrected = _mitigate_counts(counts, circuit, measurement.backend, "real_qpu",
                                             request.readout_error, properties=properties)
                point.m3_expected_cut = expected_cut(matrix, corrected)
                if scale == 1:
                    base_corrected = corrected
            except Exception as exc:
                logger.warning("M3 보정 실패: scale=%s, error_type=%s", scale, type(exc).__name__)
                report.errors[f"m3_scale_{scale}"] = "이 배율의 판독 오류를 보정하지 못했습니다."
        if scale == 1:
            report.raw_expected_cut = point.raw_expected_cut
            report.m3_expected_cut = point.m3_expected_cut
        report.samples.append(point)

    if method in {"zne", "both"} and len(report.samples) == len(request.qaoa.zne_scales):
        scales = [point.scale for point in report.samples]
        report.extrapolator = "linear"
        report.zne_expected_cut = extrapolate_linear(scales, [point.raw_expected_cut for point in report.samples])
        m3_values = [point.m3_expected_cut for point in report.samples]
        if method == "both" and all(value is not None for value in m3_values):
            report.m3_zne_expected_cut = extrapolate_linear(scales, m3_values)
    return report, base_corrected


def _sample_result(matrix, distribution, elapsed, details, *, top_k: int = 1):
    """Qiskit 비트 순서를 노드 순서로 바꾸고 실제 분할의 컷 값을 계산한다."""
    if not distribution or not all(isfinite(value) for value in distribution.values()):
        raise AlgorithmExecutionError("QAOA 측정 분포가 비어 있거나 유한하지 않습니다.")

    # Raw(top_k=1)는 단일 최빈값, Mitigated(top_k>1)는 보정 분포 상위 K개 중 최고 컷 분할 채택
    candidates = sorted(distribution.items(), key=lambda item: item[1], reverse=True)[:max(1, top_k)]
    best_bitstring = None
    best_cut = -1.0
    for raw_bits, _ in candidates:
        bs = raw_bits[::-1]
        cut = sum(
            matrix[i][j]
            for i in range(len(matrix))
            for j in range(i + 1, len(matrix))
            if bs[i] != bs[j]
        )
        if cut > best_cut:
            best_cut = cut
            best_bitstring = bs

    groups = [[node for node, bit in enumerate(best_bitstring) if bit == group] for group in "01"]
    return sampled_partition_result(
        matrix, (best_bitstring, *groups, distribution), runtime_seconds=elapsed,
        details={**details, "distribution": distribution},
    )


def run_benchmark(
    request: BenchmarkRequest, report_job: Callable[[QuantumJob], None],
    *, credentials: PersonalQpuCredentials | None = None,
) -> BenchmarkResponse:
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
        personal_failure = None
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
            gamma = [float(gamma_by_param[param]) for param in gamma_vec]
            beta = [float(beta_by_param[param]) for param in beta_vec]
            bound = bind_qaoa_parameters(circuit, gamma_vec, beta_vec, gamma, beta)
            if mode == "real_qpu":
                if request.qpu_auth == "personal" and credentials is None:
                    raise AlgorithmExecutionError("개인 QPU 실행에 IBM API 키가 필요합니다.")
                if credentials is not None:
                    personal_failure = "개인 IBM 계정에서 QPU를 선택하지 못했습니다. API 키, 인스턴스 및 장비 접근 권한을 확인하세요."
                    service = credentials.connect()
                else:
                    service = QuantumBackendManager().connect_ibm_service()
                if request.qpu_backend_name:
                    backend = service.backend(request.qpu_backend_name)
                    if backend.num_qubits < len(matrix) or backend.configuration().simulator:
                        raise AlgorithmExecutionError("선택한 IBM 장비에서 이 그래프를 측정할 수 없습니다.")
                else:
                    backend = service.least_busy(operational=True, simulator=False, min_num_qubits=len(matrix))
                if credentials is not None:
                    personal_failure = "개인 IBM QPU 작업을 처리하지 못했습니다. IBM Workloads와 인스턴스 사용량을 확인하세요."
            else:
                backend = QuantumBackendManager().get_backend(mode, request.gate_error, request.readout_error)
            # 11/18 수정 · 회로 변환과 측정에 시드를 전달하고 비교 결과에 깊이, 샷 수, 시드를 기록함.
            measured = transpile(bound.measure_all(inplace=False), backend, seed_transpiler=seed)
            folded_samples = {}
            provider_job_id = None
            folding_failed = False
            if mode == "real_qpu":
                circuits = {1: measured}
                if request.qaoa.mitigation_method in {"zne", "both"}:
                    try:
                        circuits = build_folded_measurements(measured, backend, request.qaoa.zne_scales)
                    except Exception as exc:
                        logger.warning("실제 QPU용 폴딩 회로 준비 실패: %s", type(exc).__name__)
                        folding_failed = True
                counts_list, provider_job_id = _run_qpu_job(list(circuits.values()), backend, shots, report_job)
                counts = counts_list[0]
                folded_samples = {scale: (circuits[scale], data)
                                  for scale, data in zip(list(circuits)[1:], counts_list[1:])}
            else:
                counts = _run_quantum_job(measured, backend, mode, shots, report_job, seed=seed)
            details = {
                "backend": backend.name, "p": inputs["qaoa_circuit"]["p"], "shots": shots, "seed": seed,
                "gamma": gamma, "beta": beta,
                "optimizer_expected_cut_value": float(energy + offset),
            }
            if not isfinite(details["optimizer_expected_cut_value"]):
                raise AlgorithmExecutionError("QAOA 최적화 기댓값이 유한하지 않습니다.")
            return _Measurement(counts, measured, bound, backend, operator, offset,
                                details, perf_counter() - start,
                                folded_samples, provider_job_id, folding_failed), None
        except Exception as exc:
            if personal_failure is not None:
                # SDK의 원본 예외는 키나 인스턴스를 포함할 수 있으므로 작업 로그와 응답에 전달하지 않는다.
                logger.warning("개인 IBM QPU 작업 실패: %s", type(exc).__name__)
                return None, AlgorithmExecutionError(personal_failure)
            return None, exc

    has_edges = any(weight for row in matrix for weight in row)

    @lru_cache(maxsize=1)
    def qpu_report():
        if not has_edges:
            return None, None
        measurement, error = measure()
        if error is not None:
            return None, None
        return _qpu_mitigation_report(matrix, measurement, request)

    def qaoa_result(*, mitigated):
        if not has_edges:
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
            if mode == "real_qpu":
                _, distribution = qpu_report()
                if distribution is None:
                    raise AlgorithmExecutionError("배율 1의 M3 보정 분포를 구하지 못했습니다.")
            else:
                distribution = _mitigate_counts(counts, measurement.measured_circuit, measurement.backend,
                                                mode, request.readout_error)
            elapsed += perf_counter() - start
            details = {**details, "mitigation": "m3", "distribution_type": "quasi_probability"}
            if mode == "noisy_sim":
                try:
                    from core.mitigation import run_zne_estimator

                    zne = run_zne_estimator(measurement.bound_circuit, measurement.operator,
                                            scale_factors=inputs["mitigation"]["zne_scales"],
                                            gate_error=request.gate_error, readout_error=request.readout_error,
                                            shots=shots, seed=seed)
                    # 2차 외삽이 샷 노이즈로 꺾이는 경우를 방지해 선형/2차 중 더 안정적인 값 채택
                    best_zne_energy = max(zne["zne_linear_energy"], zne["zne_richardson_energy"])
                    expected_cut = best_zne_energy + measurement.offset
                    if not all(isfinite(value) for value in [expected_cut, *zne["noisy_energies"],
                                                            zne["raw_noisy_energy"], zne["zne_linear_energy"]]):
                        raise AlgorithmExecutionError("ZNE 추정값이 유한하지 않습니다.")
                    details["zne"] = {**zne, "expected_cut_value": expected_cut}
                except Exception:
                    logger.exception("ZNE 기댓값 계산 실패")
                    details["zne_error"] = "ZNE 기댓값을 계산하지 못했습니다."
            # M3 보정 분포 상위 16개 후보 중 최고 컷 분할 선택
            return _sample_result(matrix, distribution, elapsed, details, top_k=16)
        else:
            distribution = {bits: count / total for bits, count in counts.items()}
            elapsed += perf_counter() - start
            details = {**details, "distribution_type": "probability"}
            # Raw는 노이즈가 섞인 단일 최빈값(top_k=1) 그대로 평가
            return _sample_result(matrix, distribution, elapsed, details, top_k=1)
        
    runners = [
        ("brute_force", _run_brute_force), ("sdp", _run_sdp),
        ("raw_qaoa", lambda _matrix, _inputs: qaoa_result(mitigated=False)),
    ]
    if mode != "real_qpu" or request.qaoa.mitigation_method in {"m3", "both"}:
        runners.append(("mitigated_qaoa", lambda _matrix, _inputs: qaoa_result(mitigated=True)))
    comparison = _collect_comparison(matrix, inputs, runners)
    if mode == "real_qpu":
        qem, _ = qpu_report()
        if qem and qem.errors and comparison.status == "success":
            comparison.status = "partial_success"
    else:
        qem = _simulation_report(matrix, comparison)

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
    graph_json = json.dumps([[float(value) or 0.0 for value in row] for row in matrix], separators=(",", ":"))
    return BenchmarkResponse(**comparison.model_dump(), backend=mode, benchmarks=rows,
                             request=request, graph_id=sha256(graph_json.encode()).hexdigest(), qem=qem)


def _simulation_report(matrix, comparison):
    """기존 시뮬레이션 응답의 분포와 ZNE 추정값을 공통 비교 필드에 제공한다."""
    raw = comparison.results["raw_qaoa"].result
    m3 = comparison.results["mitigated_qaoa"].result
    if not (raw or m3):
        return None
    raw_details = raw.details if raw else {}
    m3_details = m3.details if m3 else {}
    raw_dist = raw_details.get("distribution")
    m3_dist = m3_details.get("distribution")

    raw_exp = expected_cut(matrix, raw_dist) if raw_dist else None
    m3_exp = expected_cut(matrix, m3_dist) if m3_dist else None
    zne_exp = m3_details.get("zne", {}).get("expected_cut_value")

    m3_zne_exp = None
    if zne_exp is not None and m3_exp is not None and raw_exp is not None:
        m3_zne_exp = float(zne_exp + max(0.0, m3_exp - raw_exp))
    elif zne_exp is not None:
        m3_zne_exp = float(zne_exp)

    return QEMReport(
        backend_name=raw_details.get("backend") or m3_details.get("backend"),
        raw_expected_cut=raw_exp,
        m3_expected_cut=m3_exp,
        zne_expected_cut=zne_exp,
        m3_zne_expected_cut=m3_zne_exp,
    )
