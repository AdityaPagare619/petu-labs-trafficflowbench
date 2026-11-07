"""W28 bundle gates — scale-ensemble T1 inference for the candidate bundle.

Candidate = production 006G+J1 with ONLY the T1 leg replaced by the W28
scale model ensemble (mean of seed-42/43 speed+flow predictions; v2
episode/wave features; priors_scale Jun-Jan pooled; same formulation as
abs_full, scale-only training).

Feature pipeline mirrors builds/w28_t1_scale/eval_w28_build.py exactly
(TFB venv, catboost 1.2.10). Model md5s verified against STATUS.json
before inference:
  w28_scale_flow_vph_s42  e29ec2de18b996fb0a2ed3e1a14e7d29
  w28_scale_flow_vph_s43  8702cd882e21df098f146b61050d0cd9
  w28_scale_speed_kmh_s42 db730c635a036d57efee24eacebc8605
  w28_scale_speed_kmh_s43 6a8a61414e1ce8308a213c6427dc3381

Modes:
  valpriv : T1 states for Kaggle validation+private inputs (candidate CSV)
  feb     : Feb-2031-02 selection stats (ss_s/ss_f/n/sfd/guard per panel-day)
            + predicted flow fields for the K4 conservation guard
            (selection only; Feb-2031 sealed contents are never read)

Pre-declared decision rules (frozen before measuring):
  Feb selection: PASS iff dS_state_Feb (scale - production star_lam3) > 0.
  K4 guard: r = mean lwr_residual ratio (candidate / production) on matched
  Feb panel-days. CLEAN PASS r<=1.25; PASS-WITH-FLAG 1.25<r<=2.0; FAIL r>2.0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

def _resolve_tfb_root():
    """Workspace root for the award package (pure stdlib, import-time safe).

    Precedence: --root CLI arg > TFB_ROOT env var > legacy default.
    Scans sys.argv directly so imported modules see the top-level script's
    --root without argparse having run yet.
    """
    import os
    from pathlib import Path as _P
    _argv = sys.argv[1:]
    for _i, _a in enumerate(_argv):
        if _a == "--root" and _i + 1 < len(_argv):
            return _P(_argv[_i + 1]).expanduser().resolve()
        if _a.startswith("--root="):
            return _P(_a.split("=", 1)[1]).expanduser().resolve()
    _env = os.environ.get("TFB_ROOT")
    if _env:
        return _P(_env).expanduser().resolve()
    return _P("/home/hatch/workspace/tfb")


TFB = _resolve_tfb_root()
sys.path.insert(0, str(TFB / "builds/dl_blitz/tree"))
sys.path.insert(0, str(TFB / "builds/dl_blitz/mleng"))
sys.path.insert(0, str(TFB / "builds/w27_t1_scaleup"))
sys.path.insert(0, str(TFB / "builds/exp006c/kcode"))
import lane_io  # noqa: E402
import loaders  # noqa: E402
import t1_features_v2 as V  # noqa: E402
from joint_005b import build_fd, sfd_sums  # noqa: E402

W28 = TFB / "builds/w28_t1_scale"
OUT = TFB / "builds/w28_scale_bundle_gates"
DATA = TFB / "data/kaggle_public"
PANELS = lane_io.PANELS
FEAT = json.load(open(W28 / "data/t1_feat_v2_scale.json"))
ALL_FEATS = FEAT["features"]
CAT_COLS = FEAT["categorical"]

MODEL_MD5 = {
    "w28_scale_speed_kmh_s42": "db730c635a036d57efee24eacebc8605",
    "w28_scale_speed_kmh_s43": "6a8a61414e1ce8308a213c6427dc3381",
    "w28_scale_flow_vph_s42": "e29ec2de18b996fb0a2ed3e1a14e7d29",
    "w28_scale_flow_vph_s43": "8702cd882e21df098f146b61050d0cd9",
}
SEEDS = (42, 43)


def verify_models():
    for tag, want in MODEL_MD5.items():
        p = W28 / "models" / (tag + ".cbm")
        got = hashlib.md5(open(p, "rb").read()).hexdigest()
        assert got == want, f"model md5 MISMATCH {tag}: {got} vs {want}"
    print("model md5s verified (4/4)", flush=True)


def load_models():
    ms, mf = {}, {}
    for seed in SEEDS:
        for d, store in (("speed_kmh", ms), ("flow_vph", mf)):
            m = CatBoostRegressor()
            m.load_model(str(W28 / "models" / f"w28_scale_{d}_s{seed}.cbm"))
            store[seed] = m
    return ms, mf


def load_priors(panel):
    pr = np.load(W28 / "data" / f"priors_scale_{panel}.npz")
    return {"speed": pr["speed"], "flow": pr["flow"], "nslot": int(pr["nslot"])}


def load_ramps_day_split(panel: str, date: str, split: str):
    """Split-aware ramps for one date; same helper as the W27 gates script."""
    ym = date[:7]
    root = DATA / "corridors" / panel / split / "ramp_states" / f"year_month={ym}"
    if not root.exists():
        return None
    try:
        import pyarrow.dataset as ds
        dataset = ds.dataset(str(root), format="parquet", partitioning="hive")
        df = dataset.to_table().to_pandas()
    except Exception:
        return None
    if len(df) == 0:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    day = df[df["timestamp"].dt.normalize() == pd.Timestamp(date, tz="UTC")].copy()
    return day if len(day) else None


def masked_day_path(root: Path, date: str) -> Path:
    return root / f"synthetic_mainline_{date[:4]}_{date[5:7]}_{date[8:10]}.parquet"


def read_masked(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=[c for c in lane_io.MASKED_COLS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["link_id"] = df["link_id"].astype(str)
    df["station_id"] = df["station_id"].astype(str)
    return df


def predict_day(day, net, rd, priors, pi, ms, mf):
    """Mirror eval_w28_build feature path + lane ensemble definition
    (mean of the two seeds' predictions, lane: mean of per-seed scores).
    Returns (keys, ps_ens, pf_ens)."""
    X, names, keys = V.build_day_features_v2(day, net, rd, priors)
    n_ts = len(keys["timestamp"].unique())
    dfi = pd.DataFrame(X.astype(np.float32), columns=names)
    link_order = keys["link_id"].iloc[: len(keys) // n_ts].tolist()
    dfi["panel_cat"] = np.int8(pi)
    lc = pd.Categorical(keys["link_id"], categories=link_order).codes.astype(np.int32)
    dfi["link_gcode"] = (pi * 10000 + lc).astype(np.int32)
    dfi["mask_regime"] = pd.Categorical(
        keys["mask_regime"], categories=["R1", "R2", "R3"]).codes.astype(np.int8)

    Xp = dfi[ALL_FEATS].copy()
    for c in CAT_COLS:
        Xp[c] = Xp[c].astype(np.int64)

    prior_s = dfi["prior_speed"].to_numpy(dtype=float)
    prior_f = dfi["prior_flow"].to_numpy(dtype=float)
    pss, pfs = [], []
    for seed in SEEDS:
        ps = ms[seed].predict(Xp)
        pf = mf[seed].predict(Xp)
        ps = np.where(np.isfinite(ps), ps, prior_s)
        pf = np.where(np.isfinite(pf), pf, prior_f)
        pss.append(ps)
        pfs.append(pf)
    ps_ens = np.maximum(np.mean(pss, axis=0), 0.0)
    pf_ens = np.maximum(np.mean(pfs, axis=0), 0.0)
    return keys, ps_ens, pf_ens


def run_valpriv(only_panel=None, max_days=None):
    ms, mf = load_models()
    for split in ("validation", "private"):
        for pi, panel in enumerate(PANELS):
            if only_panel and panel != only_panel:
                continue
            out_csv = OUT / "cand_states" / f"cand_state_{split}_{panel}.csv"
            if out_csv.exists():
                print(f"skip (done): {out_csv.name}", flush=True)
                continue
            t0 = time.time()
            net = loaders.load_network(panel)
            priors = load_priors(panel)
            template = pd.read_csv(
                DATA / "task1" / panel / split / "sample_submission_state.csv",
                dtype=str,
                usecols=["panel", "timestamp", "station_id", "link_id",
                         "mask_regime"])
            root = DATA / "corridors" / panel / split / "mainline_states_masked"
            rows = []
            n_days = 0
            for rdir in sorted(root.glob("mask_regime=*")):
                regime = rdir.name.split("=")[1]
                for path in sorted(rdir.glob("*.parquet")):
                    date = lane_io._date_of(path)
                    day = read_masked(path)
                    rd = load_ramps_day_split(panel, date, split)
                    keys, ps, pf = predict_day(day, net, rd, priors, pi, ms, mf)
                    st_map = (day.drop_duplicates("link_id")
                              .set_index("link_id")["station_id"])
                    assert (st_map.groupby(level=0).nunique() == 1).all()
                    pred = pd.DataFrame({
                        "timestamp": keys["timestamp"].dt.strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                        "link_id": keys["link_id"].astype(str),
                        "station_id": keys["link_id"].astype(str).map(st_map),
                        "mask_regime": regime,
                        "speed_kmh": ps, "flow_vph": pf})
                    rows.append(pred)
                    n_days += 1
                    if max_days and n_days >= max_days:
                        break
                if max_days and n_days >= max_days:
                    break
            allpred = pd.concat(rows, ignore_index=True)
            merged = template.merge(
                allpred, on=["timestamp", "station_id", "link_id", "mask_regime"],
                how="left", validate="one_to_one")
            miss = int(merged["speed_kmh"].isna().sum())
            print(f"{split}/{panel}: days={n_days} template_rows={len(template)} "
                  f"unmatched={miss} t={time.time()-t0:.0f}s", flush=True)
            if not max_days:
                assert miss == 0, f"{split}/{panel}: {miss} template rows unmatched"
                merged.to_csv(out_csv, index=False)
                print(f"  wrote {out_csv.name}", flush=True)
            else:
                print(f"  (smoke mode: unmatched expected = {miss}; not written)",
                      flush=True)


def run_feb(only_panel=None, max_days=None):
    ms, mf = load_models()
    stats_path = OUT / "feb_stats.parquet"
    done_panels = set()
    if stats_path.exists() and not only_panel and not max_days:
        done_panels = set(pd.read_parquet(stats_path)["panel"].unique())
    stat_rows = []
    for pi, panel in enumerate(PANELS):
        if only_panel and panel != only_panel:
            continue
        if panel in done_panels:
            print(f"skip (done): feb {panel}", flush=True)
            continue
        t0 = time.time()
        net = loaders.load_network(panel)
        lanes_map = dict(zip(net["links"]["link_id"].astype(str),
                             net["links"]["lanes"].astype(float)))
        fd_d = build_fd(panel)
        priors = load_priors(panel)
        root = DATA / "corridors" / panel / "train" / "mainline_states_masked"
        n_days = 0
        for rdir in sorted(root.glob("mask_regime=*")):
            regime = rdir.name.split("=")[1]
            for path in sorted(rdir.glob("*2031_02_*.parquet")):
                date = lane_io._date_of(path)
                day = read_masked(path)
                rd = load_ramps_day_split(panel, date, "train")
                keys, ps, pf = predict_day(day, net, rd, priors, pi, ms, mf)
                troot = (DATA / "corridors" / panel / "train" / "mainline_states"
                         / f"year_month={date[:7]}")
                tf = sorted(troot.glob(f"*{date[:4]}_{date[5:7]}_{date[8:10]}*"))[0]
                tru = pd.read_parquet(
                    tf, columns=["timestamp", "link_id", "speed_kmh", "flow_vph",
                                 "is_score_eligible"])
                tru["timestamp"] = pd.to_datetime(tru["timestamp"], utc=True)
                tru["link_id"] = tru["link_id"].astype(str)
                m = keys.merge(tru, on=["timestamp", "link_id"], how="left")
                ok = (keys["is_target"].to_numpy()
                      & m["is_score_eligible"].fillna(False).to_numpy()
                      & np.isfinite(m["speed_kmh"].to_numpy(dtype=float))
                      & np.isfinite(m["flow_vph"].to_numpy(dtype=float)))
                tidx = np.flatnonzero(ok)
                lanes = np.array([lanes_map.get(l, 1.0)
                                  for l in keys["link_id"].iloc[tidx]])
                ds = ps[tidx] - m["speed_kmh"].to_numpy(dtype=float)[tidx]
                dq = (pf[tidx] - m["flow_vph"].to_numpy(dtype=float)[tidx]) \
                    / np.maximum(lanes, 1.0)
                num, den, gf = sfd_sums(ps[tidx], pf[tidx], fd_d,
                                        keys["link_id"].iloc[tidx].to_numpy())
                stat_rows.append({
                    "panel": panel, "date": date, "regime": regime,
                    "method": "w28_scale", "ss_s": float((ds * ds).sum()),
                    "ss_f": float((dq * dq).sum()), "n": int(len(tidx)),
                    "sfd_num": num, "sfd_den": den, "guard": gf})
                n_ts = len(keys["timestamp"].unique())
                link_order = keys["link_id"].iloc[: len(keys) // n_ts].tolist()
                q = pf.reshape(n_ts, len(link_order)).T.astype(np.float32)
                np.savez_compressed(
                    OUT / "feb_fields" / f"{panel}_{date}.npz",
                    q=q, link_order=np.array(link_order), regime=regime)
                n_days += 1
                if max_days and n_days >= max_days:
                    break
            if max_days and n_days >= max_days:
                break
        new = pd.DataFrame(stat_rows)
        if stats_path.exists() and len(new):
            old = pd.read_parquet(stats_path)
            new = pd.concat([old, new], ignore_index=True)
        new.to_parquet(stats_path, index=False)
        stat_rows = []
        print(f"feb {panel}: days={n_days} t={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["valpriv", "feb"], required=True)
    ap.add_argument("--only-panel", default=None)
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--root", default=None,
                    help="workspace root (overrides /home/hatch/workspace/tfb)")
    ap.add_argument("--from-retrain", action="store_true",
                    help="skip the .cbm file-md5 gate (retrain from scratch). "
                         "File-md5 can NEVER match after a retrain: CatBoost "
                         "regenerates a 35-byte save-time UUID on every "
                         "save_model call (verified 2026-10-12). Acceptance "
                         "in this mode is prediction-equality via "
                         "ops/award_pkg/verify_retrain.py (train_meta to 16 "
                         "digits + bit-identical 2000-row probe).")
    a = ap.parse_args()
    if a.from_retrain:
        print("WARNING: --from-retrain: skipping .cbm file-md5 gate "
              "(UUID caveat, see FROZEN_ARTIFACT_DISCLOSURE.md §4). "
              "Run ops/award_pkg/verify_retrain.py for the "
              "prediction-equality acceptance.", flush=True)
    else:
        verify_models()
    if a.mode == "valpriv":
        run_valpriv(a.only_panel, a.max_days)
    else:
        run_feb(a.only_panel, a.max_days)
