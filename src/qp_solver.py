"""Log-barrier interior-point QP solver for the T4 ODME problem.

Solves  min_f  ||A f - c||^2 + lam ||f - b||^2   s.t.  f >= 0
with A (m x n), m <= ~260, n <= ~5100. numpy + scipy only.

Method: primal log-barrier, Newton steps via Woodbury (m x m systems only).
A is used as scipy.sparse CSC (path-link incidence is ~2% dense); the slow
dense (m x n)@(n x m) product is done sparse -> ~100x faster than dense BLAS
on this box (reference BLAS).
"""
import numpy as np
import scipy.sparse as sp


def _as_csc(A):
    return A.tocsc() if sp.issparse(A) else sp.csc_matrix(np.asarray(A, dtype=float))


def _col_scale(Asc, v):
    """Return Asc with column j scaled by v[j] (new CSC matrix)."""
    out = Asc.copy()
    out.data *= np.repeat(v, np.diff(out.indptr))
    return out


def solve_qp(A, c, b, lam, mu0=0.5, mu_factor=0.2, mu_min=1e-7,
             newton_tol=1e-5, max_newton=60, f_init=None):
    Asc = _as_csc(A)
    m, n = Asc.shape
    c = np.asarray(c, dtype=float).ravel()
    b = np.asarray(b, dtype=float).ravel()
    Im = np.eye(m)

    # feasible start: unconstrained minimizer via Woodbury, floored > 0
    def woodbury_solve(Lam_inv, rhs):
        AL = _col_scale(Asc, Lam_inv)
        S = 0.5 * Im + (AL @ Asc.T).toarray()
        w = np.linalg.solve(S, AL @ rhs)
        return Lam_inv * rhs - Lam_inv * (Asc.T @ w)

    if f_init is not None:
        f = np.maximum(np.asarray(f_init, float).ravel(), 1e-10)
    else:
        ones = np.ones(n)
        Lam_inv0 = ones / (2.0 * lam)
        # (A'A+lam I)^{-1}(A'c+lam b) = (2lam I + 2A'A)^{-1} [2(A'c+lam b)]
        z = woodbury_solve(Lam_inv0, 2.0 * (Asc.T @ c + lam * b))
        f = np.maximum(z, 1e-6 * max(1.0, np.abs(z).max()))

    def obj_grad(f, mu):
        r = Asc @ f - c
        d = f - b
        J = r @ r + lam * (d @ d) - mu * np.sum(np.log(f))
        g = 2.0 * (Asc.T @ r + lam * d) - mu / f
        return J, g

    mu = mu0
    while mu >= mu_min:
        J, g = obj_grad(f, mu)
        for _ in range(max_newton):
            Lam_inv = 1.0 / (2.0 * lam + mu / (f * f))
            delta = -woodbury_solve(Lam_inv, g)
            alpha = 1.0
            gd = g @ delta
            for _ in range(60):
                fn = f + alpha * delta
                if np.all(fn > 0):
                    Jn, _ = obj_grad(fn, mu)
                    if Jn <= J + 1e-4 * alpha * gd:
                        break
                alpha *= 0.5
            f = f + alpha * delta
            J, g = obj_grad(f, mu)
            if abs(g @ delta) < newton_tol * max(1.0, abs(J)):
                break
        mu *= mu_factor

    f = np.maximum(f, 0.0)
    r = Asc @ f - c
    gg = 2.0 * (Asc.T @ r + lam * (f - b))
    info = {
        "primal_min": float(f.min()),
        "dual_min": float(gg.min()),
        "compl_max": float(np.abs(f * gg).max()),
        "obj": float(r @ r + lam * ((f - b) @ (f - b))),
    }
    return f, info


def kkt_residuals(A, c, b, lam, f):
    """KKT residuals of min ||Af-c||^2 + lam||f-b||^2 s.t. f>=0 at f."""
    Asc = _as_csc(A)
    f = np.asarray(f, float).ravel()
    r = Asc @ f - c
    g = 2.0 * (Asc.T @ r + lam * (f - b))
    return {
        "primal_feas_min_f": float(f.min()),
        "dual_feas_min_g": float(g.min()),
        "complementarity_max_fg": float(np.abs(f * g).max()),
        "stationarity_proj_resid": float(np.abs(np.maximum(f - g, 0.0) - f).max()),
        "link_resid_l1": float(np.abs(r).sum()),
        "link_resid_l2": float(np.sqrt(r @ r)),
    }


def s_link(A_rows, f, c_rows):
    A_rows = _as_csc(A_rows)
    denom = max(float(np.sum(c_rows)), 1e-9)
    return max(0.0, 1.0 - float(np.sum(np.abs(A_rows @ f - c_rows))) / denom)


def s_dev_diag(f, b):
    """DIAGNOSTIC S_dev: 1 - L1(f-b)/L1(b). Formula assumed, NOT official."""
    denom = max(float(np.sum(np.abs(b))), 1e-9)
    return max(0.0, 1.0 - float(np.sum(np.abs(f - b))) / denom)
