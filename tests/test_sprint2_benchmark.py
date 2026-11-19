"""캔버스 입력부터 Job 조회와 CSV·JSON 응답까지 API 계약을 검증한다."""
import asyncio
import csv
import json
import sys
from importlib import import_module
from io import StringIO
from threading import Event
from time import monotonic, sleep
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from starlette.datastructures import Headers

from api import benchmark, benchmark_routes, jobs
from api.benchmark_schemas import BenchmarkRequest, BenchmarkResponse, JobResponse
from api.main import app
from tests.test_api_pipeline import _check_event_loop_available
from visual.parser import parse_to_adjacency_matrix


def _http(method, path, payload=None, *, query=""):
    """별도 HTTP 클라이언트 없이 FastAPI의 라우팅과 직렬화를 거친다."""
    _check_event_loop_available()

    async def invoke():
        messages = []
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                 "query_string": query.encode(), "headers": [(b"content-type", b"application/json")],
                 "server": ("test", 80), "client": ("test", 1234), "root_path": ""}

        async def receive():
            return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)
        start = messages[0]
        body = b"".join(message.get("body", b"") for message in messages[1:])
        return start["status"], dict(start["headers"]), body

    return asyncio.run(invoke())


def _poll(path):
    deadline = monotonic() + 20
    while monotonic() < deadline:
        status, _, body = _http("GET", path)
        assert status == 200
        job = JobResponse.model_validate_json(body)
        if job.status in {"completed", "failed"}:
            return job
        sleep(0.02)
    pytest.fail("제한 시간 내에 벤치마크가 끝나지 않았습니다.")


@pytest.fixture
def local_aer_dependencies(monkeypatch):
    """IBM SDK가 비어 있는 환경에서는 로컬 코어 import에 필요한 이름만 제공한다."""
    try:
        import_module("qiskit_ibm_runtime")
    except ModuleNotFoundError as exc:
        if exc.name != "qiskit_ibm_runtime":
            raise
        sdk = ModuleType("qiskit_ibm_runtime")
        sdk.QiskitRuntimeService = object
        monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime", sdk)
        core = import_module("core")
        module_names = ("backend_manager", "optimizer", "mitigation")
        new_modules = [name for name in module_names if f"core.{name}" not in sys.modules]
        yield
        # 임시 SDK를 참조하는 코어 모듈은 이 테스트가 끝나면 제거한다.
        for name in new_modules:
            sys.modules.pop(f"core.{name}", None)
            if hasattr(core, name):
                delattr(core, name)
    else:
        yield


def test_canvas_and_dashboard_contract(monkeypatch, local_aer_dependencies):
    """실제 Aer 샷과 캔버스 입력을 사용해 조회 및 다운로드 응답을 검증한다."""
    release = Event()
    aer_jobs = []
    shared_counts = []
    run_job = benchmark._run_quantum_job

    # 11/18 수정 · 요청의 시드가 실제 Aer 측정 호출에 전달되는지 검증함.
    def tracked_run(*args, seed):
        assert seed == 23
        aer_jobs.append(1)
        counts = run_job(*args, seed=seed)
        shared_counts.append(counts)
        assert release.wait(timeout=10)
        return counts

    def corrected(counts, *_args):
        # HTTP 계약을 검사하는 동안 M3의 결과를 고정해 확률 및 엔디언을 확실히 검증한다.
        assert counts is shared_counts[0]
        return {"10": 0.8, "01": 0.3, "00": -0.1}

    monkeypatch.setattr(benchmark, "_run_quantum_job", tracked_run)
    monkeypatch.setattr(benchmark, "_mitigate_counts", corrected)
    canvas = {"nodes": [{"id": 0}, {"id": 1}],
              "edges": [{"source": 0, "target": 1, "weight": 2.5}]}
    payload = json.loads(parse_to_adjacency_matrix(canvas))
    # 11/18 수정 · 기본값과 다른 깊이, 샷 수, 시드, ZNE 배율로 Job을 요청함.
    payload.update(qaoa={"p": 3, "maxiter": 16, "shots": 128, "seed": 23, "zne_scales": [1, 5, 9]})
    try:
        status, headers, body = _http("POST", "/jobs", payload)
        assert status == 202
        queued = JobResponse.model_validate_json(body)
        assert queued.status == "queued"
        path = headers[b"location"].decode()
        assert path == f"/jobs/{queued.job_id}"
        status, headers, body = _http("GET", path)
        assert status == 200
        assert headers[b"retry-after"] == b"2"
        assert JobResponse.model_validate_json(body).status in {"queued", "running"}
        assert _http("GET", f"{path}/download")[0] == 409
    finally:
        release.set()

    completed = _poll(path)
    assert completed.status == "completed"
    assert completed.quantum_job.status == "done"
    assert completed.result.status == "success"
    assert completed.result.optimal_cut_value == 2.5
    assert len(aer_jobs) == 1
    assert [row.algorithm for row in completed.result.benchmarks] == [
        "Brute-Force", "SDP", "Raw QAOA", "Mitigated QAOA",
    ]
    # 11/18 수정 · 완화 전후 결과가 같은 깊이, 샷 수, 시드를 기록하는지 검증함.
    raw = completed.result.results["raw_qaoa"].result
    mitigated = completed.result.results["mitigated_qaoa"].result
    for result in (raw, mitigated):
        assert result.details["p"] == 3
        assert result.details["shots"] == 128
        assert result.details["seed"] == 23
    assert mitigated.bitstring == "01"
    assert mitigated.partition == [[0], [1]]
    assert mitigated.cut_value == 2.5
    # 11/18 수정 · 요청한 ZNE 배율이 외삽 결과에 반영됐는지 검증함.
    assert mitigated.details["zne"]["scale_factors"] == [1, 5, 9]
    assert mitigated.details["distribution"]["00"] == -0.1

    status, headers, body = _http("GET", f"{path}/download", query="format=json")
    assert status == 200
    assert headers[b"content-disposition"].endswith(b'.json"')
    assert BenchmarkResponse.model_validate_json(body) == completed.result
    status, headers, body = _http("GET", f"{path}/download", query="format=csv")
    assert status == 200
    assert headers[b"content-type"].startswith(b"text/csv")
    assert headers[b"content-disposition"].endswith(b'.csv"')
    rows = list(csv.DictReader(StringIO(body.decode("utf-8-sig"))))
    assert [row["algorithm"] for row in rows] == [row.algorithm for row in completed.result.benchmarks]
    assert rows[-1]["max_cut_value"] == "2.5"
    assert rows[-1]["approximation_ratio"] == "1.0"
    assert _http("GET", f"{path}/download", query="format=xml")[0] == 422


def test_validation_and_unknown_job():
    assert _http("GET", f"/jobs/{uuid4()}")[0] == 404
    assert _http("GET", "/jobs/wrong-id")[0] == 422
    assert _http("POST", "/jobs", {"adjacency_matrix": [[0, 1], [2, 0]]})[0] == 422
    assert _http("POST", "/jobs", {"matrix": [[0, 1], [1, 0]], "backend": "unknown"})[0] == 422


@pytest.mark.parametrize("field", ["matrix", "adjacency_matrix"])
def test_graph_size_limit_applies_to_both_input_aliases(field):
    valid = [[0] * 14 for _ in range(14)]
    assert BenchmarkRequest.model_validate({field: valid}).num_nodes == 14

    for oversized in ([[0] * 15 for _ in range(15)], [[0] * 15 for _ in range(2)]):
        with pytest.raises(ValidationError) as exc:
            BenchmarkRequest.model_validate({field: oversized})
        assert exc.value.errors()[0]["type"] == "too_long"


def test_full_queue_and_expired_result(monkeypatch):
    release = Event()
    clock = [0.0]
    run_benchmark = benchmark.run_benchmark

    def blocked_run(request, report_job, *, credentials=None):
        assert release.wait(timeout=10)
        return run_benchmark(request, report_job, credentials=credentials)

    monkeypatch.setattr(jobs, "monotonic", lambda: clock[0])
    monkeypatch.setattr(jobs, "run_benchmark", blocked_run)
    monkeypatch.setattr(benchmark_routes, "queue", jobs.JobQueue(workers=1, capacity=1, ttl_seconds=1))
    try:
        status, headers, _ = _http("POST", "/jobs", {"matrix": [[0, 0], [0, 0]]})
        assert status == 202
        path = headers[b"location"].decode()
        assert _http("POST", "/jobs", {"matrix": [[0, 0], [0, 0]]})[0] == 503
    finally:
        release.set()
    completed = _poll(path)
    assert completed.result.status == "success"
    assert all(row.approximation_ratio is None for row in completed.result.benchmarks)
    clock[0] = 2.0
    assert _http("GET", path)[0] == 404


def test_runtime_job_states(monkeypatch):
    """Runtime 응답을 재현하여 QPU 상태 갱신과 측정 레지스터 파싱을 확인한다."""
    states = iter(["QUEUED", "RUNNING", "DONE"])
    sdk = ModuleType("qiskit_ibm_runtime")
    backend = SimpleNamespace(name="ibm_test")
    circuit = object()
    recorded = []

    class Sampler:
        def __init__(self, *, mode):
            assert mode is backend

        def run(self, circuits, *, shots):
            assert circuits == [circuit]
            assert shots == 32
            meas = SimpleNamespace(get_counts=lambda: {"01": 32})
            return SimpleNamespace(job_id=lambda: "provider-id", status=lambda: next(states),
                                   result=lambda: [SimpleNamespace(data=SimpleNamespace(meas=meas))])

    sdk.SamplerV2 = Sampler
    monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime", sdk)
    monkeypatch.setattr(benchmark, "sleep", lambda _: None)
    assert benchmark._run_quantum_job(circuit, backend, "real_qpu", 32, recorded.append) == {"01": 32}
    assert [job.status for job in recorded] == ["queued", "running", "done"]
    assert {job.job_id for job in recorded} == {"provider-id"}


@pytest.mark.parametrize(("method", "scales"), [
    ("none", [1]), ("m3", [1]), ("zne", [1, 3, 5]), ("both", [1, 3, 5]),
])
def test_qpu_mitigation_and_download(monkeypatch, local_aer_dependencies, method, scales):
    """실제 장비 호출을 대체해 배율별 회로, 기댓값, 다운로드를 검증한다."""
    from qiskit.providers.fake_provider import GenericBackendV2
    from qiskit.quantum_info import Operator
    from core import backend_manager, optimizer

    backend = GenericBackendV2(num_qubits=4, seed=2)
    calibration_snapshot = object()
    calibration_reads = []
    corrected_counts = []
    submissions = []
    key = "test-personal-ibm-key"
    instance = "crn:v1:test-instance"
    personal = method == "both"
    by_scale = [{"01": 24, "00": 8}, {"01": 16, "00": 16}, {"01": 8, "00": 24}]
    monkeypatch.setattr(backend, "configuration", lambda: SimpleNamespace(simulator=False), raising=False)

    def read_properties():
        calibration_reads.append(1)
        return calibration_snapshot

    monkeypatch.setattr(backend, "properties", read_properties, raising=False)

    def get_backend(name):
        assert name == backend.name
        return backend

    def connect_server(_manager):
        assert not personal
        return SimpleNamespace(backend=get_backend)

    def connect_personal(*, channel, token, instance):
        assert personal
        assert (channel, token, instance) == ("ibm_quantum_platform", key, "crn:v1:test-instance")
        return SimpleNamespace(backend=get_backend)

    monkeypatch.setattr(backend_manager.QuantumBackendManager, "connect_ibm_service", connect_server)

    def optimize(_circuit, _operator, *, p, mode, **_options):
        assert mode == "ideal"
        return [0.4] * p, [0.0] * p, 0.0, []

    monkeypatch.setattr(optimizer, "optimize_qaoa_parameters", optimize)

    def correct(counts, *_args, properties):
        assert properties is calibration_snapshot
        corrected_counts.append(counts)
        probability = counts["01"] / 32 + 0.25
        return {"01": probability, "00": 1 - probability}

    monkeypatch.setattr(benchmark, "_mitigate_counts", correct)

    class Sampler:
        def __init__(self, *, mode):
            assert mode is backend

        def run(self, circuits, *, shots):
            assert len(circuits) == len(scales)
            assert shots == 32
            submissions.append(circuits)
            base = Operator(circuits[0].remove_final_measurements(inplace=False))
            for circuit in circuits:
                assert Operator(circuit.remove_final_measurements(inplace=False)).equiv(base)
                for item in circuit.data:
                    if item.operation.name != "barrier":
                        qubits = tuple(circuit.find_bit(qubit).index for qubit in item.qubits)
                        assert backend.target.instruction_supported(item.operation.name, qubits)
            results = [
                SimpleNamespace(data=SimpleNamespace(meas=SimpleNamespace(get_counts=lambda data=data: data)))
                for data in by_scale[:len(scales)]
            ]
            return SimpleNamespace(job_id=lambda: "provider-id", status=lambda: "DONE", result=lambda: results)

    sdk = sys.modules["qiskit_ibm_runtime"]
    monkeypatch.setattr(sdk, "QiskitRuntimeService", connect_personal)
    monkeypatch.setattr(sdk, "SamplerV2", Sampler, raising=False)
    queue = jobs.JobQueue(workers=1)
    monkeypatch.setattr(benchmark_routes, "queue", queue)
    request = BenchmarkRequest(
        matrix=[[0, 3], [3, 0]], backend="real_qpu", qpu_backend_name=backend.name,
        qpu_auth="personal" if personal else None,
        qaoa={"p": 1, "shots": 32, "mitigation_method": method},
    )
    if personal:
        response = Response()
        submitted = benchmark_routes.submit_job(
            request, SimpleNamespace(headers=Headers(), url_for=lambda *_args, **_kwargs: SimpleNamespace(path="/jobs")),
            response, key, instance,
        )
        assert key not in submitted.model_dump_json()
        assert response.headers["cache-control"] == "no-store"
    else:
        submitted = queue.submit(request)
    job_id = submitted.job_id
    deadline = monotonic() + 20
    while (job := queue.get(job_id)).status in {"queued", "running"}:
        assert monotonic() < deadline
        sleep(0.01)
    result = job.result
    assert job.status == "completed" and result.status == "success"
    assert len(submissions) == 1
    assert result.request == request
    assert result.job_id == job_id
    qem = result.qem
    assert qem.provider_job_id == "provider-id"
    assert qem.ideal_expected_cut == pytest.approx(1.5)
    assert qem.raw_expected_cut == pytest.approx(2.25)
    assert [point.scale for point in qem.samples] == scales
    assert [point.counts for point in qem.samples] == by_scale[:len(scales)]
    assert all(point.measurement_mapping == qem.samples[0].measurement_mapping for point in qem.samples)
    gate_counts = [point.two_qubit_gates for point in qem.samples]
    assert gate_counts[0] > 0
    assert gate_counts == [scale * gate_counts[0] for scale in scales]
    if method in {"m3", "both"}:
        assert calibration_reads == [1]
        assert corrected_counts == by_scale[:len(scales)]
        assert qem.m3_expected_cut == pytest.approx(3.0)
        assert result.results["mitigated_qaoa"].result.cut_value == 3.0
    else:
        assert not calibration_reads and not corrected_counts
        assert qem.m3_expected_cut is None
        assert "mitigated_qaoa" not in result.results
    if method in {"zne", "both"}:
        assert qem.zne_expected_cut == pytest.approx(2.625)
    else:
        assert qem.zne_expected_cut is None
    if method == "both":
        # 외삽이 최적 컷 3을 초과해도 값을 잘라내지 않는다.
        assert qem.m3_zne_expected_cut == pytest.approx(3.375)
    else:
        assert qem.m3_zne_expected_cut is None

    exported_json = benchmark_routes.download_job(job_id, format="json")
    assert BenchmarkResponse.model_validate_json(exported_json.body) == result
    exported_csv = benchmark_routes.download_job(job_id, format="csv")
    for data in (job.model_dump_json().encode(), exported_json.body, exported_csv.body):
        assert key.encode() not in data
        assert instance.encode() not in data
    rows = list(csv.DictReader(StringIO(exported_csv.body.decode("utf-8-sig"))))
    assert [row["key"] for row in rows] == [entry.key for entry in result.benchmarks]
    assert {row["graph_id"] for row in rows} == {result.graph_id}
    assert {row["p"] for row in rows} == {"1"}
    assert {row["shots"] for row in rows} == {"32"}
    assert {row["qpu_shots_used"] for row in rows} == {str(32 * len(scales))}


@pytest.mark.parametrize(("backend", "auth", "key", "instance", "duplicates"), [
    ("real_qpu", "personal", None, None, False),
    ("real_qpu", None, "", None, False),
    ("real_qpu", None, None, "crn:v1:test-instance", False),
    ("real_qpu", "personal", "private-test-key", "bad-instance", False),
    ("real_qpu", "server", "private-test-key", None, False),
    ("noisy_sim", None, "private-test-key", None, False),
    ("real_qpu", "personal", "private-test-key", None, True),
])
def test_invalid_personal_qpu_headers_do_not_queue(monkeypatch, backend, auth, key, instance, duplicates):
    def unexpected_submission(*_args, **_kwargs):
        pytest.fail("잘못된 자격 증명 요청이 큐에 등록됐습니다.")

    monkeypatch.setattr(benchmark_routes, "queue", SimpleNamespace(submit=unexpected_submission))
    headers = Headers(raw=[(b"x-ibm-api-key", b"private-test-key")] * 2 if duplicates else [])
    payload = BenchmarkRequest(matrix=[[0, 1], [1, 0]], backend=backend, qpu_auth=auth)
    with pytest.raises(HTTPException) as rejected:
        benchmark_routes.submit_job(payload, SimpleNamespace(headers=headers), Response(), key, instance)
    assert rejected.value.status_code == 400
    assert "private-test-key" not in rejected.value.detail


def test_personal_qpu_auth_failure_does_not_leak_or_fall_back(monkeypatch, local_aer_dependencies, caplog):
    from pydantic import SecretStr
    from api.qpu_credentials import PersonalQpuCredentials
    from core import backend_manager, optimizer

    key = "private-ibm-key-in-exception"
    server_calls = []
    monkeypatch.setattr(optimizer, "optimize_qaoa_parameters",
                        lambda *_args, **_kwargs: ([0.4], [0.0], 0.0, []))
    monkeypatch.setattr(backend_manager.QuantumBackendManager, "connect_ibm_service",
                        lambda _: server_calls.append(1))

    def reject(**_kwargs):
        raise RuntimeError(key)

    monkeypatch.setattr(sys.modules["qiskit_ibm_runtime"], "QiskitRuntimeService", reject)
    payload = BenchmarkRequest(
        matrix=[[0, 1], [1, 0]], backend="real_qpu", qpu_auth="personal", qaoa={"p": 1},
    )
    result = benchmark.run_benchmark(payload, lambda _: None,
                                     credentials=PersonalQpuCredentials(SecretStr(key)))
    assert result.status == "partial_success"
    assert result.results["raw_qaoa"].error.code == "invalid_result"
    assert not server_calls
    assert key not in result.model_dump_json()
    assert key not in caplog.text


def test_mitigation_failure_keeps_raw_result(monkeypatch, local_aer_dependencies):
    """샷 제출은 한 번만 하고 M3 오류가 나도 Raw 결과와 고전 기준을 보존한다."""
    submissions = []

    # 11/18 수정 · 측정 대역 함수가 새 시드 인자를 받도록 맞춤.
    def sample(*_args, seed):
        submissions.append(1)
        return {"10": 16}

    def fail(*_args):
        raise RuntimeError("내부 오류 상세")

    monkeypatch.setattr(benchmark, "_run_quantum_job", sample)
    monkeypatch.setattr(benchmark, "_mitigate_counts", fail)
    request = BenchmarkRequest(matrix=[[0, 3], [3, 0]], backend="ideal", qaoa={"maxiter": 4, "shots": 16})
    result = benchmark.run_benchmark(request, lambda _job: None)
    assert result.status == "partial_success"
    assert len(submissions) == 1
    assert result.results["raw_qaoa"].result.cut_value == 3
    assert result.results["mitigated_qaoa"].error.code == "execution_failed"
    assert result.benchmarks[-1].max_cut_value is None
    assert "내부 오류 상세" not in result.model_dump_json()


def test_m3_applies_readout_calibration():
    """M3가 설치된 환경에서 한 큐비트의 판독 보정 행렬과 준확률을 확인한다."""
    pytest.importorskip("mthree")
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(1)
    circuit.measure_all()
    corrected = benchmark._mitigate_counts({"0": 70, "1": 30}, circuit, None, "noisy_sim", 0.1)
    assert corrected == pytest.approx({"0": 0.75, "1": 0.25}, abs=1e-6)
