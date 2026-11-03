import sys
import numpy as np
import scipy
import cvxpy as cp
import qiskit
from qiskit_aer import AerSimulator

def verify():
    print(f"🐍 Python : {sys.version.split()[0]}")
    print(f"📦 Qiskit : {qiskit.__version__}")
    print(f"📦 CVXPY  : {cp.__version__}")

    # 1-qubit 회로 시뮬레이션
    qc = qiskit.QuantumCircuit(1, 1)
    qc.h(0)
    qc.measure(0, 0)
    
    sim = AerSimulator()
    result = sim.run(qc, shots=50).result().get_counts()
    print(f"✅ Aer 시뮬레이션 성공: {result}")
    print("\n🎉 VS Code 가상환경 및 라이브러리 세팅 완료!")

if __name__ == "__main__":
    verify()