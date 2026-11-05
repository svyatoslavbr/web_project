import time

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import LinearOperator, bicgstab

from app.solvers.linear import Cancelled, TimeLimitExceeded


def generate_system(n, seed, nnz_per_row=5):
    rng = np.random.default_rng(seed)
    rows = np.repeat(np.arange(n), nnz_per_row)
    cols = rng.integers(0, n, size=n * nnz_per_row)
    vals = rng.uniform(-1.0, 1.0, size=n * nnz_per_row)
    a = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    row_sums = np.asarray(abs(a).sum(axis=1)).ravel()
    a = (a + sp.diags(row_sums + 1.0)).tocsr()
    x_true = rng.uniform(-1.0, 1.0, size=n)
    b = a @ x_true
    return a, b, x_true


def solve_sparse(a, b, report, should_cancel, time_limit, rtol=1e-8, maxiter=2000):
    started = time.monotonic()
    diag = a.diagonal()
    precond = LinearOperator(a.shape, matvec=lambda v: v / diag)
    b_norm = np.linalg.norm(b)
    state = {"iterations": 0, "best": 10}

    def callback(xk):
        if should_cancel():
            raise Cancelled
        if time.monotonic() - started > time_limit:
            raise TimeLimitExceeded
        state["iterations"] += 1
        rel = np.linalg.norm(b - a @ xk) / b_norm
        fraction = min(1.0, np.log10(1.0 / max(rel, 1e-300)) / 8)
        state["best"] = max(state["best"], 10 + int(85 * fraction))
        report(state["best"], f"Ітерація {state['iterations']}, залишок {rel:.1e}")

    x, info = bicgstab(a, b, rtol=rtol, maxiter=maxiter, M=precond, callback=callback)
    if info != 0:
        raise ValueError("Ітераційний метод не збігся")
    return x, state["iterations"]
