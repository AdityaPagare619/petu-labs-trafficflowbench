"""W27 T1 features v2: base (v1) + EPISODE features + WAVE-ASYMMETRIC cone features.

Design (MATH_DESIGN.md):
- CLM-0076: innovation is episode-shaped -> same-day episode context features.
- CLM-0072 (C4): wave propagation is asymmetric (downstream fast ~vf,
  upstream tail slow 1-5 km/h) -> cone features at wave-consistent lags.

All features computed from the MASKED day + static network only (no truth).
Row order matches t1_features.build_day_features: t-major, link-minor (n*L).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

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


sys.path.insert(0, str(_resolve_tfb_root() / "builds/dl_blitz/tree"))
import t1_features as T  # noqa: E402


def _link_order(day: pd.DataFrame, net: dict) -> list[str]:
    links = net["links"].copy()
    links["link_id"] = links["link_id"].astype(str)
    mp = day.dropna(subset=["milepost"]).drop_duplicates("link_id").set_index(
        "link_id")["milepost"]
    if len(mp) == 0 and "topology" in net and "order_index" in net["topology"].columns:
        topo = net["topology"].copy()
        lkcol = "mainline_link_id" if "mainline_link_id" in topo.columns else "link_id"
        mp = topo.drop_duplicates(lkcol).set_index(lkcol)["order_index"]
    links["milepost"] = links["link_id"].map(mp)
    links = links.sort_values("milepost").reset_index(drop=True)
    return links["link_id"].tolist()


def _lag(mat: np.ndarray, steps: int) -> np.ndarray:
    """Time-lag a (n, L) matrix by `steps` (positive = past). NaN-padded."""
    out = np.full_like(mat, np.nan)
    if steps == 0:
        return mat.copy()
    if steps > 0:
        out[steps:] = mat[:-steps]
    else:
        out[:steps] = mat[-steps:]
    return out


def _shift_links(mat: np.ndarray, k: int) -> np.ndarray:
    """Shift link axis by k (positive k: value at l comes from l-k, i.e. upstream)."""
    out = np.full_like(mat, np.nan)
    if k == 0:
        return mat.copy()
    if k > 0:
        out[:, k:] = mat[:, :-k]
    else:
        out[:, :k] = mat[:, -k:]
    return out


def build_day_features_v2(day, net, ramps_day, priors):
    X0, names0, keys = T.build_day_features(day, net, ramps_day, priors)

    link_order = _link_order(day, net)
    L = len(link_order)
    ts = np.sort(pd.to_datetime(day["timestamp"].unique(), utc=True).to_numpy())
    n = len(ts)
    assert n * L == X0.shape[0], (n, L, X0.shape)

    spd = T._pivot(day, "speed_kmh", link_order, ts)
    flw = T._pivot(day, "flow_vph", link_order, ts)
    vf = net["links"].copy()
    vf["link_id"] = vf["link_id"].astype(str)
    vf = vf.set_index("link_id").reindex(link_order)
    vf_link = vf["free_speed_kmh"].to_numpy(dtype=float)          # (L,)
    vf_panel = float(np.nanmean(vf_link))

    names: list[str] = []
    blocks: list[np.ndarray] = []

    def add(name, arr):
        names.append(name)
        blocks.append(np.asarray(arr, dtype=np.float64).reshape(n, L))

    # ---------------- EPISODE FEATURES (same-day context) ----------------
    obs = ~np.isnan(spd)
    panel_mean = np.nanmean(np.where(obs, spd, np.nan), axis=1)     # (n,)
    panel_mean_filled = pd.Series(panel_mean).ffill().bfill().to_numpy()
    day_mean = float(np.nanmean(panel_mean))
    # deviation of current panel state from the day's mean level
    add("epi_state_dev", np.broadcast_to((panel_mean_filled - day_mean)[:, None], (n, L)))
    # early-day anchor (first 24 steps = 2h): the day's demand level, self-calibrating
    anchor = float(np.nanmean(panel_mean[:24])) if n >= 6 else day_mean
    add("epi_anchor", np.full((n, L), anchor))
    add("epi_anchor_ratio", np.broadcast_to((panel_mean_filled / max(anchor, 1.0))[:, None], (n, L)))
    # cross-link dispersion (episodes coherent, noise not)
    disp = np.nanstd(np.where(obs, spd, np.nan), axis=1)
    disp = pd.Series(disp).ffill().bfill().fillna(0.0).to_numpy()
    add("epi_disp", np.broadcast_to(disp[:, None], (n, L)))
    # episode age: steps since panel mean last >= 0.85*vf_panel
    thresh = 0.85 * vf_panel
    above = panel_mean_filled >= thresh
    age = np.zeros(n)
    last = -1
    for t in range(n):
        if above[t]:
            last = t
        age[t] = (t - last) if last >= 0 else t + 1
    add("epi_age", np.broadcast_to(age[:, None], (n, L)))
    # cumulative speed deficit (episode severity integral)
    deficit = np.cumsum(np.maximum(0.0, vf_panel - panel_mean_filled))
    add("epi_cumdef", np.broadcast_to(deficit[:, None], (n, L)))
    # flow episode analog
    panel_flw = np.nanmean(np.where(~np.isnan(flw), flw, np.nan), axis=1)
    panel_flw = pd.Series(panel_flw).ffill().bfill().to_numpy()
    add("epi_flow_dev", np.broadcast_to((panel_flw - float(np.nanmean(panel_flw)))[:, None], (n, L)))

    # ---------------- WAVE-ASYMMETRIC CONES (CLM-0072) ----------------
    # link index increases downstream (milepost ascending).
    # Downstream congestion spills BACK upstream slowly (tail 1-5 km/h):
    # state of downstream links a few steps ago predicts congestion arriving.
    add("wv_dn1_lag1", _shift_links(_lag(spd, 1), -1))   # downstream nb, 5 min ago
    add("wv_dn1_lag3", _shift_links(_lag(spd, 3), -1))   # downstream nb, 15 min ago
    add("wv_dn2_lag3", _shift_links(_lag(spd, 3), -2))   # 2-down, 15 min ago
    add("wv_dn1_lag6", _shift_links(_lag(spd, 6), -1))   # downstream nb, 30 min ago
    # Upstream vehicles arrive at ~free-flow (fast): recent upstream state.
    add("wv_up1_lag1", _shift_links(_lag(spd, 1), 1))    # upstream nb, 5 min ago
    add("wv_up1_lag0", _shift_links(spd, 1))             # upstream nb, now
    add("wv_up2_lag1", _shift_links(_lag(spd, 1), 2))    # 2-up, 5 min ago
    # flow cones (same geometry, flow channel)
    add("wv_dn1_lag3_f", _shift_links(_lag(flw, 3), -1))
    add("wv_up1_lag1_f", _shift_links(_lag(flw, 1), 1))
    # cone observation support (how much of the spillback cone is observed)
    cone_obs = (~np.isnan(_shift_links(_lag(spd, 3), -1))).astype(float) \
        + (~np.isnan(_shift_links(_lag(spd, 1), 1))).astype(float) \
        + (~np.isnan(_shift_links(_lag(spd, 6), -1))).astype(float)
    add("wv_cone_cnt", cone_obs / 3.0)

    # ---------------- LOCAL OBSERVATION DENSITY ----------------
    obsf = obs.astype(float)
    dens = pd.DataFrame(obsf).rolling(5, min_periods=1, center=True).mean().to_numpy()
    dens = np.stack([np.nanmean(dens[:, max(0, l - 2):l + 3], axis=1) for l in range(L)], axis=1)
    add("loc_obs_frac", dens)

    Xnew = np.stack(blocks, axis=-1).reshape(n * L, len(names))
    X = np.hstack([X0, Xnew])
    return X, names0 + names, keys
