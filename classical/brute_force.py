"""두 그룹을 서로 바꾸면 같은 컷이 되는 대칭성을 이용해 Max-Cut을 완전탐색한다."""

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from numpy.typing import ArrayLike

from .common import CutResult, _edge_arrays, positive_integer, prepare_adjacency_matrix


@dataclass(frozen=True)
class BruteForceResult(CutResult):
    evaluated_cuts: int


def brute_force_max_cut(adjacency: ArrayLike, *, max_nodes: int = 14) -> BruteForceResult:
    """정확한 최적해를 구하며, 노드 수가 max_nodes를 초과하면 실행하지 않는다.

    0번 노드를 그룹 0에 고정하고 나머지 노드의 2**(n-1)개 배정을 조사한다.
    n은 노드 수, m은 간선 수이며, 노드 수는 공통 코어 기준인 2~14개를 따른다.
    시간 복잡도는 O(n**2 + (n + m) * 2**(n-1)), 공간 복잡도는 O(n**2 + m)이다.
    최댓값이 같으면 탐색 순서에서 먼저 발견한 배정을 유지한다.
    """
    start = perf_counter()
    max_nodes = positive_integer(max_nodes, "max_nodes")
    weights = prepare_adjacency_matrix(adjacency)
    n = len(weights)
    if n > max_nodes:
        raise ValueError(f"Brute-force is limited to {max_nodes} nodes; received {n}")
    rows, cols, edge_weights = _edge_arrays(weights)
    best_bits = np.zeros(n, dtype=np.int8)
    best_value = 0.0
    count = 1 << max(0, n - 1)
    for mask in range(count):
        bits = np.zeros(n, dtype=np.int8)
        for node in range(1, n):
            bits[node] = (mask >> (node - 1)) & 1
        value = float(edge_weights[bits[rows] != bits[cols]].sum())
        if value > best_value:
            best_value, best_bits = value, bits.copy()
    return BruteForceResult(
        algorithm="brute_force", assignment=tuple(map(int, best_bits)),
        cut_value=best_value, runtime_seconds=perf_counter() - start,
        evaluated_cuts=count,
    )
