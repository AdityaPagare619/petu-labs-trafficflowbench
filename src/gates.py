"""W28 bundle gates — Feb selection comparison, K4 conservation guard,
Regime Gate labels, deflated-significance and bundle-LOO arithmetic.

Runs AFTER infer_w28.py (needs ../feb_stats.parquet + feb_fields/).
Feb production baseline: builds/exp006k/kout_feb shards, cfg star_lam3
(= production 006K, lam_c=0.3, lam_fd=3.0). W27 abs_full Feb stats for the
marginal-vs-leader read: builds/w27_bundle_gates/feb_stats.parquet
(method abs_full). Aggregation replicates builds/w27_t1_scaleup/report_w27.py.
Feb-2031 sealed contents are never read (selection only, one frozen run).
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

def _resolve_tfb_root():
    """Workspace root for the award package (pure stdlib, import-time safe).

    Precedence: --root CLI arg > TFB_ROOT env var > legacy default.
    Scans sys.argv directly so imported modules see the top-level script's
    --root without argparse having run yet.
    """
    import os
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


TFB = _resolve_tfb_root()
sys.path.insert(0, str(TFB / "builds/dl_blitz/tree"))
sys.path.insert(0, str(TFB / "builds/dl_blitz/mleng"))
sys.path.insert(0, str(TFB / "builds/exp006c/kcode"))
OUT = TFB / "builds/w28_scale_bundle_gates"
W27G = TFB / "builds/w27_bundle_gates"
W28 = TFB / "builds/w28_t1_scale"


def s_state_from(df):
    g = df.groupby(["panel", "regime"])[["ss_s", "ss_f", "n"]].sum()
    g["rmse_s"] = np.sqrt(g["ss_s"] / g["n"])
    g["rmse_f"] = np.sqrt(g["ss_f"] / g["n"])
    g["S"] = 0.54 * np.maximum(0, 1 - g["rmse_s"] / 25.0) \
        + 0.46 * np.maximum(0, 1 - g["rmse_f"] / 600.0)
    gg = g.reset_index()
    gg["fam"] = gg["panel"].str.rsplit("_", n=1).str[0]
    return float(gg.groupby("fam")["S"].mean().mean())


def s_fd_from(df):
    d = df.dropna(subset=["sfd_num"])
    g = d.groupby(["panel", "regime"])[["sfd_num", "sfd_den"]].sum()
    g["S_FD"] = (1 - g["sfd_num"] / (g["sfd_den"] + 1e-9)).clip(lower=0)
    gg = g.reset_index()
    gg["fam"] = gg["panel"].str.rsplit("_", n=1).str[0]
    return float(gg.groupby("fam")["S_FD"].mean().mean())


def paired_day_boot(df_test, df_ref, fn, B=2000, seed=20310301):
    """Day-paired bootstrap of fn(test)-fn(ref) on shared (panel,date) days."""
    rng = np.random.default_rng(seed)
    t = df_test.copy(); r = df_ref.copy()
    t["k"] = list(zip(t["panel"], t["date"]))
    r["k"] = list(zip(r["panel"], r["date"]))
    keys = sorted(set(t["k"]) & set(r["k"]))
    tm = {k: t[t["k"] == k] for k in keys}
    rm = {k: r[r["k"] == k] for k in keys}
    by_panel = {}
    for k in keys:
        by_panel.setdefault(k[0], []).append(k)
    out = np.empty(B)
    for b in range(B):
        ts, rs = [], []
        for p, ks in by_panel.items():
            pick = rng.choice(len(ks), len(ks), replace=True)
            for i in pick:
                ts.append(tm[ks[i]]); rs.append(rm[ks[i]])
        out[b] = fn(pd.concat(ts)) - fn(pd.concat(rs))
    return out


def feb_comparison():
    cand = pd.read_parquet(OUT / "feb_stats.parquet")
    sh = pd.concat([pd.read_parquet(f) for f in glob.glob(
        str(TFB / "builds/exp006k/kout_feb/feb_shard_006k_*.parquet"))])
    prod = sh[sh["cfg"] == "star_lam3"].copy()
    res = {}
    res["prod_S_state"] = s_state_from(prod)
    res["cand_S_state"] = s_state_from(cand)
    res["dS_state"] = res["cand_S_state"] - res["prod_S_state"]
    res["prod_S_FD"] = s_fd_from(prod)
    res["cand_S_FD"] = s_fd_from(cand)
    res["dS_FD"] = res["cand_S_FD"] - res["prod_S_FD"]
    d = paired_day_boot(cand, prod, s_state_from)
    res["dS_state_boot"] = {"mean": float(d.mean()), "se": float(d.std(ddof=1)),
                            "lo": float(np.percentile(d, 2.5)),
                            "hi": float(np.percentile(d, 97.5)),
                            "p_le0": float((d <= 0).mean()),
                            "z": float(d.mean() / d.std(ddof=1))}
    d = paired_day_boot(cand, prod, s_fd_from)
    res["dS_FD_boot"] = {"mean": float(d.mean()), "se": float(d.std(ddof=1)),
                         "lo": float(np.percentile(d, 2.5)),
                         "hi": float(np.percentile(d, 97.5)),
                         "p_le0": float((d <= 0).mean())}
    per = {}
    for p in sorted(set(cand["panel"]) & set(prod["panel"])):
        per[p] = s_state_from(cand[cand["panel"] == p]) \
            - s_state_from(prod[prod["panel"] == p])
    res["per_panel_dS_state"] = per
    # marginal vs the W27 bundle leader on the same Feb days (abs_full stats)
    ab = pd.read_parquet(W27G / "feb_stats.parquet")
    res["w27_absfull_S_state_feb"] = s_state_from(ab)
    d2 = paired_day_boot(cand, ab, s_state_from)
    res["dS_state_scale_minus_absfull_feb"] = {
        "mean": float(d2.mean()), "se": float(d2.std(ddof=1)),
        "lo": float(np.percentile(d2, 2.5)), "hi": float(np.percentile(d2, 97.5)),
        "p_le0": float((d2 <= 0).mean())}
    return res


def k4_guard():
    """Same relative conservation-residual guard as W27: candidate flow
    fields (feb_fields) vs production's shard lwr (star_lam3, res_after),
    production's ruler: joint_005b.lwr_residual / pairs_from_topology."""
    from joint_005b import lwr_residual, pairs_from_topology, ramp_grids
    sh = pd.concat([pd.read_parquet(f) for f in glob.glob(
        str(TFB / "builds/exp006k/kout_feb/feb_shard_006k_*.parquet"))])
    prod = sh[sh["cfg"] == "star_lam3"][["panel", "date", "lwr"]]
    rows = []
    for f in sorted((OUT / "feb_fields").glob("*.npz")):
        parts = f.stem.rsplit("_", 1)
        date = parts[1]
        panel = f.stem[: -(len(date) + 1)]
        z = np.load(f, allow_pickle=True)
        q = z["q"].astype(float)
        links = np.asarray([str(x) for x in z["link_order"]])
        iu, idn = pairs_from_topology(panel, links)
        R, rho = ramp_grids(panel, date, links, split="train")
        rows.append({"panel": panel, "date": date,
                     "lwr_cand": lwr_residual(q, iu, idn, R, rho),
                     "n_pairs": len(iu)})
    c = pd.DataFrame(rows)
    m = c.merge(prod, on=["panel", "date"], how="inner")
    m["ratio"] = m["lwr_cand"] / m["lwr"]
    res = {"matched_days": int(len(m)),
           "prod_lwr_mean": float(m["lwr"].mean()),
           "cand_lwr_mean": float(m["lwr_cand"].mean()),
           "ratio_of_means": float(m["lwr_cand"].mean() / m["lwr"].mean()),
           "median_day_ratio": float(m["ratio"].median()),
           "p95_day_ratio": float(m["ratio"].quantile(0.95)),
           "n_pairs_median": float(m["n_pairs"].median())}
    return res


def regime_labels():
    sys.path.insert(0, str(TFB / "builds/w26_wave/lane2_regime_gate"))
    import regime_gate as rg
    out = {}
    for mo in ["2030-10", "2030-11", "2030-12", "2031-01"]:
        try:
            out[mo] = rg.d3_for_month(mo)
        except Exception as e:
            out[mo] = f"UNAVAILABLE ({type(e).__name__})"
    try:
        out["2031-02"] = rg.d3_for_month("2031-02")
    except Exception as e:
        out["2031-02"] = f"SEALED — gate fails closed ({type(e).__name__})"
    out["board_refs"] = {"2031-03": 0.03908, "2031-04": 0.03954}
    return out


def loo_vs_w27():
    """Bundle LOO: marginal of the T1 swap vs the W27 bundle leader
    (0.81458 board), from lane-measured method-level numbers
    (w28_scale_summary.json, adjudicated)."""
    s = json.load(open(W28 / "data/w28_scale_summary.json"))
    dS_state = s["ensemble"]["mean"]            # +0.00594 vs abs_full
    lo, hi = s["ensemble"]["lo"], s["ensemble"]["hi"]
    dS_fd = s["sfd_delta"]["mean"]              # +0.00061 vs abs_full
    # measurable part of the bundle delta: 0.35*T1 + 0.15/3*(S_FD+2*S_LWR);
    # S_LWR treated as parity (K4-adjudicated below), same convention as W27.
    marginal = 0.35 * dS_state + 0.15 * dS_fd / 3.0
    marginal_lo = 0.35 * lo + 0.15 * dS_fd / 3.0
    return {"dS_state_vs_absfull": dS_state, "ci_lo": lo, "ci_hi": hi,
            "dS_FD_vs_absfull": dS_fd,
            "bundle_marginal_vs_w27": float(marginal),
            "bundle_marginal_lo": float(marginal_lo),
            "drop_bar": 0.002,
            "pass": bool(marginal > 0.002)}


def _save(res):
    (OUT / "gates_results.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    res = {}
    print("computing Feb comparison...", flush=True)
    res["feb"] = feb_comparison()
    _save(res)
    print("computing K4 guard...", flush=True)
    res["k4"] = k4_guard()
    _save(res)
    print("computing regime labels...", flush=True)
    res["regime"] = regime_labels()
    _save(res)
    print("computing LOO vs W27...", flush=True)
    res["loo"] = loo_vs_w27()
    _save(res)
    print(json.dumps(res, indent=2))
