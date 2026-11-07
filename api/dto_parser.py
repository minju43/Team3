from pydantic import BaseModel, Field
from typing import List

class EdgeDTO(BaseModel):
    source: int
    target: int
    weight: float = Field(default=1.0)

class GraphInputDTO(BaseModel):
    num_nodes: int
    edges: List[EdgeDTO]

def parse_graph_input(data: dict) -> GraphInputDTO:
    return GraphInputDTO(**data)