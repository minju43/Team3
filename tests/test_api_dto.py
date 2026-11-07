from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

class EdgeDTO(BaseModel):
    """그래프의 간선(Edge) 정보를 담는 DTO"""
    source: int = Field(..., ge=0, description="시작 노드 인덱스")
    target: int = Field(..., ge=0, description="도착 노드 인덱스")
    weight: float = Field(1.0, description="간선의 가중치 (기본값 1.0)")

class MaxCutRequestDTO(BaseModel):
    """Max-Cut 문제 해결을 위한 클라이언트 요청 DTO"""
    num_nodes: int = Field(..., gt=0, description="그래프의 전체 노드 수")
    edges: List[EdgeDTO] = Field(..., description="그래프 간선 목록")
    algorithm: str = Field("qaoa", description="사용할 알고리즘 (qaoa, brute-force, sdp)")
    qaoa_p: Optional[int] = Field(1, ge=1, description="QAOA 회로의 깊이(p) 파라미터")

    # Pydantic V2 방식의 설정 (ConfigDict 적용)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "num_nodes": 3,
                "edges": [
                    {"source": 0, "target": 1, "weight": 1.0},
                    {"source": 1, "target": 2, "weight": 1.0}
                ],
                "algorithm": "qaoa",
                "qaoa_p": 1
            }
        }
    )