"""
QAOA 양자-고전 하이브리드 최적화 루프 (에너지 최대화 픽스 & 노이즈 백엔드 연동)
Task ID: T5, US-03, US-12
"""
import numpy as np
from scipy.optimize import minimize
from qiskit_aer.primitives import Estimator as AerEstimator
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp
from core.backend_manager import QuantumBackendManager


def optimize_qaoa_parameters(
    qc: QuantumCircuit,
    hamiltonian: SparsePauliOp,
    p: int = 1,
    maxiter: int = 100,
    mode: str = "ideal",
    gate_error: float = 0.01,
    readout_error: float = 0.03,
    shots: int = 1024
):
    # 1. 모드에 따른 Estimator 설정 (이상적 모드일 때는 노이즈 없는 Aer Estimator 사용)
    if mode == "ideal":
        estimator = AerEstimator()
    elif mode == "noisy_sim":
        manager = QuantumBackendManager()
        noise_model = manager.get_custom_noise_model(
            gate_error_prob=gate_error,
            readout_error_prob=readout_error
        )
        estimator = AerEstimator(
            backend_options={"noise_model": noise_model},
            run_options={"shots": shots}
        )
    else:
        estimator = AerEstimator()


    energy_history = []

    # p >= 2 일 때 인덱스 순서가 섞이지 않도록 이름 기준 정렬
    g_params = sorted([param for param in qc.parameters if "gamma" in param.name], key=lambda x: x.name)
    b_params = sorted([param for param in qc.parameters if "beta" in param.name], key=lambda x: x.name)

    def objective_function(param_values):
        g_vals = param_values[:p]
        b_vals = param_values[p:]

        param_dict = {}
        for g_p, g_v in zip(g_params, g_vals):
            param_dict[g_p] = float(g_v)
        for b_p, b_v in zip(b_params, b_vals):
            param_dict[b_p] = float(b_v)

        bound_qc = qc.assign_parameters(param_dict)
        job = estimator.run(bound_qc, hamiltonian)
        energy = float(job.result().values[0])

        energy_history.append(energy)

        # T3 해밀토니안은 에너지가 높을수록 정답이므로 마이너스 부호를 붙여 최대화 유도
        return -energy

    # 0000의 평탄한 함정에 빠지지 않도록 시작 각도를 비틀어줌
    initial_params = np.array([0.5, 1.0] * p)

    result = minimize(
        objective_function,
        initial_params,
        method="COBYLA",
        options={"maxiter": maxiter, "disp": False}
    )

    opt_gamma = result.x[:p]
    opt_beta = result.x[p:]

    # 최종 결과 반환 시에는 마이너스를 다시 떼고 원래 에너지 값으로 복구해서 리턴
    return opt_gamma, opt_beta, float(-result.fun), energy_history