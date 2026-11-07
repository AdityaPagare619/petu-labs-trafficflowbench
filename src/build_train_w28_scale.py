"""W28 overnight data prep: build the abs_full-scale training shard.

Same formulation/pipeline as W27 build_train_w27.py — EXACT reuse of
t1_features_v2.build_day_features_v2, t1_features.build_priors,
rows_from_features, subsample_day, augment_day (parameterized by rate).

Documented diffs vs W27 (see DATA_CARD.md):
  D1: TRAIN_MONTHS = 2030-06..2031-01 (8 months) instead of 2030-06..09 (4).
  D2: days stratified per panel-month (N_DAYS_PER_MONTH) instead of 5 pooled.
  D3: three aug rates AUG_RATES=[0.20,0.30,0.50] instead of a single 0.30
      (matches the competitor's 20/30/50% masking census; W27's docstring
      referenced it, its shard only contained 0.30).
  D4: new column aug_rate (float32; 0.0 for natural rows) alongside W27's aug flag.
  D5: priors built from 30 days pooled across the 8 train months (W27: 4).
  D6: per-panel shards + train-days manifest (needed so the morning blinded
      Oct-Jan eval can exclude these exact dates).

No modeling, no training, no eval, no Feb-2031. Memory-safe: one panel in
memory at a time, write shard, gc.
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

TFB = Path("/home/hatch/workspace/tfb")
sys.path.insert(0, str(TFB / "builds/dl_blitz/tree"))
sys.path.insert(0, str(TFB / "builds/dl_blitz/mleng"))
sys.path.insert(0, str(TFB / "builds/w27_t1_scaleup"))
import lane_io  # noqa: E402
import loaders  # noqa: E402
import t1_features as T  # noqa: E402
import t1_features_v2 as V  # noqa: E402

W28 = TFB / "builds/w28_t1_scale"
SEED = 42
TRAIN_MONTHS = ["2030-06", "2030-07", "2030-08", "2030-09",
                "2030-10", "2030-11", "2030-12", "2031-01"]
AUG_RATES = [0.20, 0.30, 0.50]
N_PRIOR_DAYS = 30
N_DAYS_PER_MONTH = int(sys.argv[2]) if len(sys.argv) > 2 else 4
ROWS_PER_DAY = 3000
PANELS_ARG = sys.argv[1] if len(sys.argv) > 1 else "all"
BLANK_COLS = ["speed_kmh", "flow_vph", "occupancy", "density_occ_linear_vehpkm"]


def masked_day(panel, date, regime):
    root = lane_io.DATA_ROOT / "corridors" / panel / "train" / "mainline_states_masked"
    f = sorted(root.glob(f"mask_regime={regime}/*{date[:4]}_{date[5:7]}_{date[8:10]}*"))[0]
    df = pd.read_parquet(f, columns=[c for c in lane_io.MASKED_COLS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["link_id"] = df["link_id"].astype(str)
    return df


def truth_map(panel, dates):
    need = set(dates)
    out = {}
    for month in TRAIN_MONTHS:
        for d, df in lane_io.iter_truth_days(panel, month):
            if d in need:
                out[d] = df
    return out


def rows_from_features(X, names, keys, tday, pi, lo, aug_flag, aug_rate,
                       only_keys=None):
    tgt = tday[["timestamp", "link_id", "speed_kmh", "flow_vph",
                "is_score_eligible"]].copy()
    m = keys.merge(tgt, on=["timestamp", "link_id"], how="left")
    ok = (m["is_target"] & m["is_score_eligible"].fillna(False)
          & m["speed_kmh"].notna() & m["flow_vph"].notna()).to_numpy()
    if only_keys is not None:
        kidx = pd.MultiIndex.from_frame(m[["timestamp", "link_id"]])
        ok = ok & kidx.isin(only_keys)
    idx = np.flatnonzero(ok)
    if len(idx) == 0:
        return None
    df = pd.DataFrame(X[idx].astype(np.float32), columns=names)
    df["speed_kmh"] = m["speed_kmh"].to_numpy()[idx]
    df["flow_vph"] = m["flow_vph"].to_numpy()[idx]
    df["panel_cat"] = np.int8(pi)
    lc = pd.Categorical(keys["link_id"].iloc[idx], categories=lo).codes.astype(np.int32)
    df["link_gcode"] = (pi * 10000 + lc).astype(np.int32)
    df["mask_regime"] = pd.Categorical(
        keys["mask_regime"].iloc[idx], categories=["R1", "R2", "R3"]).codes.astype(np.int8)
    df["aug"] = np.int8(aug_flag)
    df["aug_rate"] = np.float32(aug_rate)
    return df


def subsample_day(df, rng):
    cong = (df["speed_kmh"] < 60).to_numpy()
    keep_c = df[cong]
    rest = df[~cong]
    n_keep = max(0, ROWS_PER_DAY - len(keep_c))
    if len(rest) > n_keep:
        rest = rest.sample(n=n_keep, random_state=SEED)
    return pd.concat([keep_c, rest], ignore_index=True)


def augment_day(day, tday, rng, rate):
    """Blank extra observed+eligible cells: rate% iid + a 12-step episode
    block on rate% of links (W27 structure, rate parameterized)."""
    elig = tday.set_index(["timestamp", "link_id"])["is_score_eligible"]
    obs = day[day["speed_kmh"].notna()][["timestamp", "link_id"]].copy().reset_index(drop=True)
    key = pd.MultiIndex.from_frame(obs)
    e = elig.reindex(key).fillna(False).to_numpy().astype(bool)
    obs = obs.iloc[np.flatnonzero(e)].reset_index(drop=True)
    if len(obs) == 0:
        return day, None
    pick = rng.random(len(obs)) < rate
    chosen = obs.iloc[np.flatnonzero(pick)]
    ts_sorted = np.sort(day["timestamp"].unique())
    if len(ts_sorted) > 24:
        t0 = int(rng.integers(0, len(ts_sorted) - 12))
        win = set(ts_sorted[t0:t0 + 12])
        links = obs["link_id"].unique()
        bl = set(rng.choice(links, size=max(1, int(rate * len(links))), replace=False))
        blk = obs[obs["timestamp"].isin(win) & obs["link_id"].isin(bl)]
        chosen = pd.concat([chosen, blk]).drop_duplicates()
    aug = day.copy()
    ck = pd.MultiIndex.from_frame(aug[["timestamp", "link_id"]])
    sel = ck.isin(pd.MultiIndex.from_frame(chosen))
    aug.loc[sel, BLANK_COLS] = np.nan
    return aug, pd.MultiIndex.from_frame(chosen)


def rss_mb():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def build_panel(pi, panel, outdir):
    t0 = time.time()
    rng = np.random.default_rng(SEED + pi * 7919)
    net = loaders.load_network(panel)
    # date pools per month
    month_days = {}
    day_regime = {}
    for month in TRAIN_MONTHS:
        days = [(d, r) for d, r, _ in lane_io.iter_masked_days(panel, month)]
        for d, r in days:
            day_regime[d] = r
        month_days[month] = [d for d, _ in days]
    sel_days = []
    for month in TRAIN_MONTHS:
        pool = month_days[month]
        k = min(N_DAYS_PER_MONTH, len(pool))
        sel_days.extend(sorted(rng.choice(pool, size=k, replace=False).tolist()))
    pr_pool = sorted({d for ds in month_days.values() for d in ds})
    pr_days = sorted(rng.choice(pr_pool, size=min(N_PRIOR_DAYS, len(pr_pool)),
                                replace=False).tolist())
    tmap = truth_map(panel, sorted(set(sel_days) | set(pr_days)))
    lo = None
    priors = None
    all_rows = []
    feat_names = None
    manifest = []
    for date in sel_days:
        regime = day_regime.get(date, "R1")
        day = masked_day(panel, date, regime)
        tday = tmap[date]
        if lo is None:
            lo = (day.dropna(subset=["milepost"]).drop_duplicates("link_id")
                  .sort_values("milepost")["link_id"].astype(str).tolist())
            tframes = [tmap[d] for d in pr_days if d in tmap]
            priors = T.build_priors(tframes, lo)
        try:
            rd = lane_io.load_ramps_day(panel, date)
        except Exception:
            rd = None
        X, names, keys = V.build_day_features_v2(day, net, rd, priors)
        feat_names = names
        manifest.append({"panel": panel, "panel_idx": pi, "date": date,
                         "regime": regime, "role": "natural"})
        df = rows_from_features(X, names, keys, tday, pi, lo, 0, 0.0)
        if df is not None:
            all_rows.append(subsample_day(df, rng))
        del X, keys, df
        for rate in AUG_RATES:
            aug_day, chosen_keys = augment_day(day, tday, rng, rate)
            if chosen_keys is not None and len(chosen_keys):
                Xa, _, keya = V.build_day_features_v2(aug_day, net, rd, priors)
                manifest.append({"panel": panel, "panel_idx": pi, "date": date,
                                 "regime": regime, "role": f"aug_{rate:.2f}"})
                dfa = rows_from_features(Xa, names, keya, tday, pi, lo, 1,
                                         rate, only_keys=chosen_keys)
                if dfa is not None:
                    all_rows.append(subsample_day(dfa, rng))
                del Xa, keya, dfa, aug_day
        del day, tday
        gc.collect()
    print(f"[{panel}] days={len(sel_days)} rows={sum(map(len, all_rows))} "
          f"rss={rss_mb():.0f}MB t={time.time()-t0:.0f}s", flush=True)
    data = pd.concat(all_rows, ignore_index=True)
    del all_rows
    gc.collect()
    shard = outdir / f"train_abs_scale_p{pi:02d}.parquet"
    data.to_parquet(shard, index=False)
    manifest_df = pd.DataFrame(manifest)
    manifest_df.to_parquet(outdir / f"train_days_manifest_p{pi:02d}.parquet",
                           index=False)
    if priors is not None:
        np.savez_compressed(outdir / f"priors_scale_{panel}.npz",
                            speed=priors["speed"], flow=priors["flow"],
                            nslot=priors["nslot"])
    print(f"[{panel}] wrote {shard.name} {data.shape} natural="
          f"{int((data['aug']==0).sum())} aug20="
          f"{int((data['aug_rate']==0.20).sum())} aug30="
          f"{int((data['aug_rate']==0.30).sum())} aug50="
          f"{int((data['aug_rate']==0.50).sum())} rss={rss_mb():.0f}MB "
          f"t={time.time()-t0:.0f}s", flush=True)
    return feat_names, data.shape


def main():
    t0 = time.time()
    outdir = W28 / "data"
    outdir.mkdir(parents=True, exist_ok=True)
    if PANELS_ARG == "all":
        panels = list(enumerate(lane_io.PANELS))
    else:
        idxs = [int(x) for x in PANELS_ARG.split(",")]
        panels = [(i, lane_io.PANELS[i]) for i in idxs]
    feat_names = None
    for pi, panel in panels:
        feat_names, _ = build_panel(pi, panel, outdir)
        gc.collect()
    feature_cols = (feat_names + ["panel_cat", "link_gcode", "mask_regime"])
    json.dump({"features": feature_cols,
               "categorical": ["link_gcode", "panel_cat", "mask_regime"],
               "train_months": TRAIN_MONTHS, "aug_rates": AUG_RATES,
               "n_days_per_month": N_DAYS_PER_MONTH,
               "rows_per_day": ROWS_PER_DAY, "seed": SEED,
               "diff_vs_w27": ["D1 train months 8 vs 4",
                               "D2 stratified per-panel-month vs pooled",
                               "D3 aug rates [0.20,0.30,0.50] vs [0.30]",
                               "D4 new column aug_rate",
                               "D5 priors pooled over 8 months",
                               "D6 per-panel shards + day manifest"]},
              open(outdir / "t1_feat_v2_scale.json", "w"), indent=1)
    print(f"DONE panels={[p for _, p in panels]} "
          f"n_days_per_month={N_DAYS_PER_MONTH} t={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
