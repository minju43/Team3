"""Goemans-Williamson 알고리즘의 SDP 완화와 무작위 초평면 라운딩을 구현한다."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any
import warnings

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .common import CutResult, _edge_arrays, positive_integer, prepare_adjacency_matrix


@dataclass(frozen=True)
class SDPResult(CutResult):
    sdp_objective: float
    solver_status: str
    solver: str
    rounds: int
    seed: int | None


def _embedding(matrix: NDArray[np.float64], *, tolerance: float = 1e-4) -> NDArray[np.float64]:
    """X = V V.T로 분해하고, 솔버의 수치 오차로 생긴 작은 음의 고윳값만 0으로 보정한다."""
    if not np.isfinite(matrix).all():
        raise RuntimeError("SDP solver returned nonfinite matrix entries")
    symmetric = (matrix + matrix.T) / 2
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    if np.max(np.abs(np.diag(symmetric) - 1)) > tolerance or eigenvalues.min() < -tolerance:
        raise RuntimeError("SDP solution violates feasibility tolerance; tighten solver settings")
    vectors = eigenvectors * np.sqrt(np.maximum(eigenvalues, 0))
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(lengths == 0):
        raise RuntimeError("SDP solution contains a zero-length vector")
    return vectors / lengths


def goemans_williamson_max_cut(
    adjacency: ArrayLike, *, rounds: int = 256, seed: int | None = 0,
    solver: str = "SCS", solver_options: dict[str, Any] | None = None,
) -> SDPResult:
    """가중 Max-Cut의 SDP 완화 문제를 풀고 무작위 컷 중 최선의 결과를 반환한다.

    X가 양의 준정부호(PSD)이고 diag(X)=1일 때 (1/4) sum_ij w_ij (1-X_ij)를 최대화한다.
    가중치가 음이 아니고 SDP를 정확하게 풀면 무작위 라운딩의 기대 근사비는
    0.87856 이상이다. 유한 횟수의 수치 계산만으로 이 보장을 인증할 수는 없다.
    sdp_objective는 SDP 완화 목적값의 수치 추정치이며, 인증된 상한값은 아니다.
    """
    start = perf_counter()
    rounds = positive_integer(rounds, "rounds")
    if seed is not None:
        if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
            raise ValueError("seed must be a nonnegative integer or None")
        seed = int(seed)
    if not isinstance(solver, str) or not solver:
        raise ValueError("solver must be a nonempty solver name")
    options = dict(solver_options or {})
    if {"solver", "warm_start", "ignore_dpp", "enforce_dpp", "requires_grad"} & options.keys():
        raise ValueError("solver_options must contain solver settings only")
    weights = prepare_adjacency_matrix(adjacency)
    n = len(weights)
    rows, cols, edge_weights = _edge_arrays(weights)
    if not len(edge_weights):
        return SDPResult(
            algorithm="goemans_williamson", assignment=(0,) * n,
            cut_value=0.0, runtime_seconds=perf_counter() - start,
            sdp_objective=0.0, solver_status="not_run", solver=solver,
            rounds=0, seed=seed,
        )

    import cvxpy as cp

    if solver not in cp.installed_solvers():
        raise ValueError(f"Solver {solver!r} is not installed; available: {cp.installed_solvers()}")
    # 가중치를 정규화해 솔버의 허용 오차가 가중치 단위에 영향을 받지 않도록 한다.
    scale = float(edge_weights.max())
    scaled_weights = weights / scale
    x = cp.Variable((n, n), PSD=True)
    problem = cp.Problem(
        cp.Maximize(cp.sum(cp.multiply(scaled_weights, 1 - x)) / 4),
        [cp.diag(x) == 1],
    )
    if solver == "SCS":
        options = {"eps": 1e-6, "max_iters": 100_000, **options}
    try:
        problem.solve(solver=solver, **options)
    except cp.error.SolverError as exc:
        raise RuntimeError(f"SDP solver {solver} failed: {exc}") from exc
    if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) or x.value is None:
        raise RuntimeError(f"SDP solver did not return a solution: {problem.status}")
    if problem.value is None or not np.isfinite(problem.value):
        raise RuntimeError("SDP solver returned a nonfinite objective")
    if problem.status == cp.OPTIMAL_INACCURATE:
        warnings.warn("SDP solver returned optimal_inaccurate; inspect solver settings",
                      RuntimeWarning, stacklevel=2)
    vectors = _embedding(np.asarray(x.value, dtype=float))
    rng = np.random.default_rng(seed)
    best_value = 0.0
    best_bits = np.zeros(n, dtype=np.int8)
    for _ in range(rounds):
        bits = (vectors @ rng.standard_normal(n) >= 0).astype(np.int8)
        if bits[0]:
            bits = 1 - bits
        value = float(edge_weights[bits[rows] != bits[cols]].sum())
        if value > best_value:
            best_value, best_bits = value, bits.copy()
    # 같은 간선을 두 번 세지 않도록 인접 행렬의 상삼각 부분만 계산한다.
    sdp_value = float(np.dot(edge_weights, (1 - x.value[rows, cols]) / 2))
    if not np.isfinite(sdp_value):
        raise RuntimeError("SDP objective exceeds float64 range")
    return SDPResult(
        algorithm="goemans_williamson", assignment=tuple(map(int, best_bits)),
        cut_value=best_value, runtime_seconds=perf_counter() - start,
        sdp_objective=sdp_value, solver_status=str(problem.status),
        solver=solver, rounds=rounds, seed=seed,
    )
