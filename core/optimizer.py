"""
QAOA 양자-고전 하이브리드 최적화 루프 (에너지 최대화 픽스)
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
    estimator = Estimator()
    energy_history = []
    
    g_params = [param for param in qc.parameters if "gamma" in param.name]
    b_params = [param for param in qc.parameters if "beta" in param.name]

    def objective_function(param_values):
        g_vals = param_values[:p]
        b_vals = param_values[p:]
        
        param_dict = {}
        for g_p, g_v in zip(g_params, g_vals):
            param_dict[g_p] = g_v
        for b_p, b_v in zip(b_params, b_vals):
            param_dict[b_p] = b_v
            
        bound_qc = qc.assign_parameters(param_dict)
        job = estimator.run(bound_qc, hamiltonian)
        energy = job.result().values[0]
        
        energy_history.append(energy)
        
        # [결정적 해결책] T3 해밀토니안은 에너지가 '높을수록' 정답입니다.
        # minimize 함수가 강제로 에너지를 최대화(Maximize)하도록 마이너스 부호를 붙여서 리턴합니다.
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
    return opt_gamma, opt_beta, -result.fun, energy_history