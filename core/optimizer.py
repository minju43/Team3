"""
QAOA 양자-고전 하이브리드 최적화 루프 (COBYLA)
Task ID: T5
"""
import numpy as np
from scipy.optimize import minimize
from qiskit.primitives import Estimator
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

def optimize_qaoa_parameters(
    qc: QuantumCircuit,
    hamiltonian: SparsePauliOp,
    p: int = 1,
    maxiter: int = 100
):
    """
    COBYLA 고전 최적화기를 사용해 QAOA 회로의 최적 파라미터를 찾습니다.
    """
    # Qiskit의 기댓값(에너지) 계산기
    estimator = Estimator()
    energy_history = []

    def objective_function(param_values):
        # 1. 현재 파라미터를 회로에 꽂고 해밀토니안 에너지를 계산 (시뮬레이션)
        job = estimator.run(qc, hamiltonian, parameter_values=[param_values])
        energy = job.result().values[0]
        
        # 2. 진행 과정 기록
        energy_history.append(energy)
        return energy

    # 초기 파라미터 무작위 설정 (gamma p개, beta p개)
    np.random.seed(42)  # 테스트 재현성을 위해 시드 고정
    initial_params = np.random.uniform(-np.pi, np.pi, 2 * p)

    # Scipy 최적화기(COBYLA) 실행: 에너지가 최소가 될 때까지 다이얼을 꺾음
    result = minimize(
        objective_function,
        initial_params,
        method="COBYLA",
        options={"maxiter": maxiter, "disp": False}
    )

    # 최적화된 결과를 gamma와 beta 배열로 분리
    opt_gamma = result.x[:p]
    opt_beta = result.x[p:]

    return opt_gamma, opt_beta, result.fun, energy_history