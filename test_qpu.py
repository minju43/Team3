# test_qpu.py
from core.backend_manager import QuantumBackendManager

print("=== [IBM Quantum 서비스 연결 테스트] ===")
manager = QuantumBackendManager()

try:
    # 1. 서비스 연결 확인
    service = manager.connect_ibm_service()
    print("▶ IBM Quantum 서비스 연결 성공!")

    # 2. 사용 가능한 실제 QPU 장비 중 가장 덜 바쁜 기기(least_busy) 가져오기
    backend = manager.get_backend(mode="real_qpu")
    print(f"▶ 할당된 실제 QPU 장비 이름: {backend.name}")
    print(f"▶ 큐비트 수: {backend.num_qubits}")
    print(f"▶ 상태: {'가동 중 (Operational)' if backend.status().operational else '점검 중'}")
    print(f"▶ 대기 중인 잡(Job) 수: {backend.status().pending_jobs}")

except Exception as e:
    print(f"❌ 연결 실패 또는 토큰 오류: {e}")