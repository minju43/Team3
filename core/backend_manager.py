# core/backend_manager.py
import os
from typing import Optional
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
from qiskit_ibm_runtime import QiskitRuntimeService

class QuantumBackendManager:
    """
    실제 IBM QPU, 하드웨어 모사 노이즈 시뮬레이터, 커스텀 노이즈 모델을 
    통합 관리하는 백엔드 매니저 (US-03, US-12 대응)
    """
    def __init__(self, ibm_token: Optional[str] = None):
        self.token = ibm_token or os.getenv("IBM_QUANTUM_TOKEN")
        self.service: Optional[QiskitRuntimeService] = None

    def connect_ibm_service(self) -> QiskitRuntimeService:
        """IBM Quantum 플랫폼에 연결합니다."""
        if not self.service:
            if self.token:
                self.service = QiskitRuntimeService(
                    channel="ibm_cloud", 
                    token=self.token
                )
            else:
                # 로컬에 이미 저장된 자격증명이 있는 경우
                self.service = QiskitRuntimeService(channel="ibm_cloud")
        return self.service

    def get_custom_noise_model(
        self, 
        gate_error_prob: float = 0.01, 
        readout_error_prob: float = 0.03
    ) -> NoiseModel:
        """
        [US-12] 게이트 오류율과 측정(Readout) 오류율을 직접 조절할 수 있는 
        커스텀 노이즈 모델을 생성합니다.
        """
        noise_model = NoiseModel()

        # 1. 1큐비트(rx) 및 2큐비트(rzz, cx) 게이트 탈분극(Depolarizing) 노이즈
        if gate_error_prob > 0:
            error_1q = depolarizing_error(gate_error_prob, 1)
            error_2q = depolarizing_error(min(gate_error_prob * 2, 1.0), 2)
            noise_model.add_all_qubit_quantum_error(error_1q, ['rx', 'rz', 'sx', 'x'])
            noise_model.add_all_qubit_quantum_error(error_2q, ['rzz', 'cx', 'ecr'])

        # 2. 측정(Readout) 판독 오차 (0을 1로, 1을 0으로 잘못 읽을 확률)
        if readout_error_prob > 0:
            p0g1 = readout_error_prob  # 1인데 0으로 읽을 확률
            p1g0 = readout_error_prob  # 0인데 1로 읽을 확률
            readout_err = ReadoutError([
                [1.0 - p1g0, p1g0], 
                [p0g1, 1.0 - p0g1]
            ])
            noise_model.add_all_qubit_readout_error(readout_err)

        return noise_model

    def get_backend(
        self, 
        mode: str = "noisy_sim", 
        gate_error: float = 0.01, 
        readout_error: float = 0.03
    ):
        """
        실행 모드에 맞는 백엔드 객체를 반환합니다.
        - 'ideal': 노이즈 없는 이상적 시뮬레이터 (기존 Sprint 1 방식)
        - 'noisy_sim': 노이즈가 주입된 시뮬레이터 (오류 완화 검증용)
        - 'real_qpu': 실제 IBM 양자 컴퓨터 (대기열 가장 짧은 기기 자동 선택)
        """
        if mode == "ideal":
            return AerSimulator()
            
        elif mode == "noisy_sim":
            noise_model = self.get_custom_noise_model(gate_error, readout_error)
            return AerSimulator(noise_model=noise_model)
            
        elif mode == "real_qpu":
            service = self.connect_ibm_service()
            # 시뮬레이터가 아닌 실제 가동 중인 양자 기기 중 가장 덜 바쁜(least_busy) 기기 반환
            backend = service.least_busy(operational=True, simulator=False, min_num_qubits=4)
            return backend
            
        else:
            raise ValueError(f"지원하지 않는 백엔드 모드입니다: {mode}")