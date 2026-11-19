"""요청 하나에서만 사용하는 IBM Quantum 자격 증명."""

from dataclasses import dataclass, field

from pydantic import SecretStr


@dataclass(frozen=True)
class PersonalQpuCredentials:
    api_key: SecretStr
    instance: str | None = field(default=None, repr=False)

    def connect(self):
        from qiskit_ibm_runtime import QiskitRuntimeService

        return QiskitRuntimeService(
            channel="ibm_quantum_platform",
            token=self.api_key.get_secret_value(),
            instance=self.instance,
        )
