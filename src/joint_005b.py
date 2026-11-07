"""EXP-005B library: joint T1+T3 conservation-constrained interpolation.

Implements MATH_DESIGN.md:
  J(q) = (q - qbar)^T M (q - qbar) + lam_c * (A q - R)^T P_w (A q - R)
  KKT: (M + lam_c * A^T P_w A) q = M qbar + lam_c * A^T P_w R   (SPD -> CG)

  qbar = observed flows at observed cells, Q1 q_hat elsewhere.
  M    = diag(W_obs) on observed cells, mu_0 elsewhere.
  A    = pair-incidence over topological consecutive mainline pairs
         (incoming/outgoing_link_ids from lwr_mainline_topology.csv;
          linear sections only; never from_node/to_node).
  R    = net ramp flow (OR - FR) attached to the upstream link of each pair,
         same-day ramp states (L4-allowed same-day conditioning).
  P_w  = diag(rho): rho=1 iff the pair-time is Mode-A scoreable
         (no ramps attached, or every attached ramp cell valid per the
         official pct_observed>=75 & eligible & finite rule); else 0.

Reuses Q1 (predict_day_q, frozen weights_q1.json, coh_power=2.0) as the
interpolant anchor, and the official-style stat accumulators.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import cg

def _resolve_tfb_root():
    """Workspace root for the award package (pure stdlib, import-time safe).

    Precedence: --root CLI arg > TFB_ROOT env var > legacy default.
    Scans sys.argv directly so imported modules see the top-level script's
    --root without argparse having run yet.
    """
    import os
    from pathlib import Path
    _argv = sys.argv[1:]
    for _i, _a in enumerate(_argv):
        if _a == "--root" and _i + 1 < len(_argv):
            return Path(_argv[_i + 1]).expanduser().resolve()
        if _a.startswith("--root="):
            return Path(_a.split("=", 1)[1]).expanduser().resolve()
    _env = os.environ.get("TFB_ROOT")
    if _env:
        return Path(_env).expanduser().resolve()
    return Path("/home/hatch/workspace/tfb")


sys.path.insert(0, str(_resolve_tfb_root() / "builds/exp002e"))
sys.path.insert(0, str(_resolve_tfb_root() / "builds/exp002g"))
sys.path.insert(0, str(_resolve_tfb_root() / "builds/exp002p"))
sys.path.insert(0, str(_resolve_tfb_root() / "builds/exp002q"))

from exp002e_lib import TFB, CORR, link_order, fd_params, load_day, build_matrices  # noqa: E402
from exp002g_lib import regime_of_day  # noqa: E402
from exp002q_lib import predict_day_q  # noqa: E402

W_OBS = 1e4   # fidelity precision pinning bit-exact observed cells
MU0 = 1.0     # anchor precision at unobserved cells
T_STEPS = 288


# --------------------------------------------------------------------------
# topology pairs (incoming/outgoing_link_ids; never from_node/to_node)
# --------------------------------------------------------------------------
def pairs_from_topology(panel, grid_links):
    """Consecutive mainline pairs (u, d) as grid-row index pairs.

    d in outgoing_link_ids(u), both in the panel link set, linear sections
    only (u: exactly one mainline outgoing; d: exactly one mainline
    incoming). Returns (iu, id) int arrays aligned with grid_links order.
    """
    topo = pd.read_csv(CORR / panel / "network" / "lwr_mainline_topology.csv",
                       dtype=str)
    topo["link_id"] = topo["link_id"].astype(str)
    main = set(grid_links.tolist())
    row_of = {l: i for i, l in enumerate(grid_links)}

    def split_ids(s):
        return [x.strip() for x in str(s).split(";") if x.strip()]

    out_map, in_map = {}, {}
    for _, r in topo.iterrows():
        lid = r["link_id"]
        if lid not in main:
            continue
        out_map[lid] = [x for x in split_ids(r.get("outgoing_link_ids", "")) if x in main]
        in_map[lid] = [x for x in split_ids(r.get("incoming_link_ids", "")) if x in main]
    iu, idn = [], []
    for u in grid_links:
        u = str(u)
        outs = [d for d in out_map.get(u, []) if d != u]
        if len(outs) != 1:
            continue
        d = outs[0]
        ins = [x for x in in_map.get(d, []) if x != d]
        if len(ins) != 1 or ins[0] != u:
            continue
        iu.append(row_of[u])
        idn.append(row_of[d])
    return np.array(iu, dtype=np.int64), np.array(idn, dtype=np.int64)


# --------------------------------------------------------------------------
# ramp grids with official validity -> (R, rho)
# --------------------------------------------------------------------------
def ramp_grids(panel, date, grid_links, split="train"):
    """Net ramp flow R[u,t] and Mode-A scoreability rho[u,t] per link.

    R = sum(valid OR) - sum(valid FR) attached to link u (via
    ramp_attachment_map.csv nearest_mainline_link_id), same-day ramp states.
    A ramp cell is valid iff is_score_eligible & pct_observed>=75 & finite
    (mirrors vendor load_ramp_flows). rho[u,t]=1 iff (no ramps attached to u)
    or (every attached ramp valid at t); else 0.

    split: which data split's ramp_states to read ("train" default for
    pseudo-val; "validation"/"private" for production). Added for the
    wave-5 production bundle; default keeps all experiment call sites
    unchanged.
    """
    L = len(grid_links)
    R = np.zeros((L, T_STEPS))
    rho = np.ones((L, T_STEPS))  # default: no ramps attached -> scoreable
    attach = pd.read_csv(CORR / panel / "network" / "ramp_attachment_map.csv",
                         dtype=str)
    attach["ramp_link_id"] = attach["ramp_link_id"].astype(str)
    attach["nearest_mainline_link_id"] = attach["nearest_mainline_link_id"].astype(str)
    row_of = {str(l): i for i, l in enumerate(grid_links)}
    attach = attach[attach["nearest_mainline_link_id"].isin(row_of)].copy()
    if attach.empty:
        return R, rho
    attached_rows = np.array([row_of[l] for l in attach["nearest_mainline_link_id"]])

    ym = f"year_month={date[:7]}"
    f = (CORR / panel / split / "ramp_states" / ym /
         f"synthetic_ramp_{date.replace('-', '_')}.parquet")
    rho[:, :] = 0.0
    # links with no attached ramps stay rho=1
    has_att = np.zeros(L, dtype=bool)
    has_att[attached_rows] = True
    rho[~has_att, :] = 1.0
    if not f.exists():
        return R, rho  # attached links: rho=0 (no data -> misspecified)
    df = pd.read_parquet(f, columns=["timestamp", "ramp_link_id", "ramp_type",
                                     "flow_vph", "pct_observed",
                                     "is_score_eligible"])
    if df.empty:
        return R, rho
    df["ramp_link_id"] = df["ramp_link_id"].astype(str)
    amap = dict(zip(attach["ramp_link_id"], attach["nearest_mainline_link_id"]))
    df = df[df["ramp_link_id"].isin(amap)].copy()
    if df.empty:
        return R, rho
    df["ml_row"] = df["ramp_link_id"].map(amap).map(row_of)
    rt = df["ramp_type"].astype(str).str.upper()
    df["is_on"] = rt.isin(["OR", "ON"]).to_numpy()
    df["is_off"] = rt.isin(["FR", "OFF"]).to_numpy()
    df["fl"] = pd.to_numeric(df["flow_vph"], errors="coerce").to_numpy(float)
    df["pct"] = pd.to_numeric(df["pct_observed"], errors="coerce").to_numpy(float)
    df["elig"] = df["is_score_eligible"].astype(str).str.lower().isin(
        ["true", "1"]).to_numpy()
    df["valid"] = df["elig"] & (df["pct"] >= 75.0) & np.isfinite(df["fl"])
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df["_t"] = (ts.dt.hour * 12 + ts.dt.minute // 5).to_numpy(dtype=np.int64)
    df = df[(df["_t"] >= 0) & (df["_t"] < T_STEPS)]
    if df.empty:
        return R, rho
    # net flow from valid cells only
    dfv = df[df["valid"]].copy()
    if not dfv.empty:
        dfv["signed"] = np.where(dfv["is_on"], dfv["fl"],
                                 np.where(dfv["is_off"], -dfv["fl"], 0.0))
        g = dfv.groupby(["ml_row", "_t"])["signed"].sum()
        for (li, ti), v in g.items():
            R[int(li), int(ti)] += float(v)
    # rho: every attached ramp valid at (u,t)
    # a link-time is scoreable iff all its attached ramps are valid then
    df["att_key"] = list(zip(df["ml_row"].to_numpy(), df["_t"].to_numpy()))
    allg = df.groupby("att_key")["valid"].agg(["all", "count"])
    for (li, ti), row in allg.iterrows():
        if bool(row["all"]):
            rho[int(li), int(ti)] = 1.0
    return R, rho


# --------------------------------------------------------------------------
# joint solve  (M + lam A^T P_w A) q = M qbar + lam A^T P_w R
# --------------------------------------------------------------------------
def build_system(qbar, mu, iu, idn, R, rho, lam):
    """Assemble sparse SPD system. Link-major flattening: idx = l*T + t."""
    L, T = qbar.shape
    assert T == T_STEPS
    n = L * T
    base = np.arange(L, dtype=np.int64) * T  # link base offsets
    t = np.tile(np.arange(T, dtype=np.int64), len(iu))
    iu_rep = np.repeat(iu, T)
    id_rep = np.repeat(idn, T)
    gi_u = base[iu_rep] + t
    gi_d = base[id_rep] + t
    w = rho[iu_rep, t] * lam  # per-pair-time weight (rho on upstream link)

    # diagonal: mu + lam * sum of incident pair weights; off-diagonal: -lam*w
    # (single assembly path: COO entries summed by tocsr(); no separate add.at)
    diag = mu.ravel().copy()
    rows = np.concatenate([np.arange(n), gi_u, gi_d, gi_u, gi_d])
    cols = np.concatenate([np.arange(n), gi_u, gi_d, gi_d, gi_u])
    data = np.concatenate([diag, w, w, -w, -w])
    H = sparse.coo_matrix((data, (rows, cols)), shape=(n, n)).tocsr()
    H.sum_duplicates()

    b = (mu * qbar).ravel().copy()
    rvec = R[iu_rep, t]  # net ramp on upstream link
    np.add.at(b, gi_u, -w * rvec)
    np.add.at(b, gi_d, w * rvec)
    return H, b


def cg_solve(H, b, x0=None, tol=1e-9):
    try:
        x, info = cg(H, b, x0=x0, rtol=tol, atol=0.0, maxiter=2000)
    except TypeError:  # older scipy: tol kwarg
        x, info = cg(H, b, x0=x0, tol=tol, maxiter=2000)
    if info != 0:
        raise RuntimeError(f"CG failed to converge (info={info})")
    return x


def solve_joint(q_anchor, mu, iu, idn, R, rho, lam, x0=None):
    """Exact minimizer of J(q). Returns q* shaped (L, T)."""
    H, b = build_system(q_anchor, mu, iu, idn, R, rho, lam)
    x = cg_solve(H, b, x0=x0)
    return x.reshape(q_anchor.shape)


# --------------------------------------------------------------------------
# day-level driver: Q1 -> joint q*
# --------------------------------------------------------------------------
def predict_day_joint(panel, date, prof, fb, od, fd, W, csp, cfl,
                      iu, idn, R_ramp, rho_ramp, lam, x0=None,
                      cap_clip=True):
    """Q1 reconstruction with flow replaced by the joint solution.

    Returns (r, info) where r is the predict_day_q dict with r['q_hat']
    overwritten by the conservation-constrained field (clipped), and info
    carries diagnostics (lwr residuals before/after, CG iters).
    """
    from exp002e_lib import build_matrices, load_day
    r = predict_day_q(panel, date, prof, fb, od, fd, W,
                      coh_spd=csp, coh_flo=cfl,
                      coh_cfg={"R1": {"power": 2.0, "dist_decay": True},
                               "R2": {"power": 2.0, "dist_decay": True},
                               "R3": {"power": 2.0, "dist_decay": True}},
                      fam_cfg=None, perlane=False)
    m, _ = load_day(panel, date, split="train", need_truth=True)
    mats = build_matrices(m, od)
    assert (np.asarray(r["links"]).astype(str) ==
            np.asarray(mats["links"]).astype(str)).all(), "grid misaligned"
    obs = np.asarray(mats["obs"], dtype=bool)
    y = np.asarray(mats["flo"], dtype=float)

    L = len(r["links"])
    q_q1 = np.asarray(r["q_hat"], dtype=float)
    qbar = np.where(obs, np.where(np.isfinite(y), y, q_q1), q_q1)
    mu = np.where(obs, W_OBS, MU0).astype(float)

    # LWR residual before (diagnostic, rho-weighted pairs)
    res_before = lwr_residual(q_q1, iu, idn, R_ramp, rho_ramp)

    q_star = solve_joint(qbar, mu, iu, idn, R_ramp, rho_ramp, lam, x0=x0)
    if cap_clip:
        cap = fd_params(panel)["capacity_vph"].reindex(
            pd.Index(np.asarray(r["links"]).astype(str))).to_numpy(float)
        q_star = np.clip(q_star, 0.0, 1.15 * cap[:, None])
    res_after = lwr_residual(q_star, iu, idn, R_ramp, rho_ramp)

    r = dict(r)
    r["q_hat"] = q_star
    info = {"lwr_before": res_before, "lwr_after": res_after,
            "n_pairs": len(iu), "rho_mean": float(rho_ramp.mean())}
    return r, info


def lwr_residual(q, iu, idn, R, rho):
    """Mean |q_d - q_u - R_u| over scoreable (rho>0.5) pair-times."""
    if len(iu) == 0:
        return float("nan")
    w = rho[iu] > 0.5  # (n_pairs, T)
    res = q[idn][:, :] - q[iu][:, :] - R[iu]
    m = w & np.isfinite(res)
    return float(np.abs(res[m]).mean()) if m.any() else float("nan")


# --------------------------------------------------------------------------
# stat helpers (vendored small fns from exp003i/run_003i.py, attributed)
# --------------------------------------------------------------------------
def build_fd(panel):
    fp = fd_params(panel)
    fd = {}
    for lid, rr in fp.iterrows():
        lid = str(lid)
        vf = float(rr["free_speed_kmh"])
        cap = float(rr["capacity_vph"])
        kcrit = float(rr["critical_density"])
        kjam = float(rr["k_jam"])
        fd[lid] = {"vf": vf, "cap": cap, "lanes": float(rr["lanes"]),
                   "k_crit": kcrit, "k_jam": kjam,
                   "wave_speed": cap / max(kjam - kcrit, 1e-9)}
    return fd


def sfd_sums(pred_speed, pred_flow, fd, link_ids):
    """Official-style S_FD sufficient stats on the given cells (per-lane)."""
    lids = np.asarray(link_ids, dtype=str)
    p = [fd[l] for l in lids]
    lanes = np.array([x["lanes"] for x in p]).clip(min=1.0)
    v = np.maximum(pred_speed, 1.0)
    k_lane = (pred_flow / v) / lanes
    q_lane = pred_flow / lanes
    cap_lane = np.array([x["cap"] for x in p]) / lanes
    kcrit = np.array([x["k_crit"] for x in p]) / lanes
    kjam = np.array([x["k_jam"] for x in p]) / lanes
    vf = np.array([x["vf"] for x in p])
    w = cap_lane / np.maximum(kjam - kcrit, 1e-9)
    q_fd = np.where(k_lane <= kcrit, vf * k_lane,
                    w * np.maximum(kjam - k_lane, 0.0))
    num = float(np.abs(q_lane - q_fd).sum())
    den = float(np.abs(q_lane).sum())
    guard_frac = float((pred_flow < 50.0).mean())
    return num, den, guard_frac
