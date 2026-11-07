"""D1 FIX (gated lane w57): rebuild T1 link x slot priors PER SCORED SPLIT.

Identical construction rule to the shipped priors (t1_features.build_priors,
as called by builds/w28_t1_scale/build_train_w28_scale.py:177 on 30 pooled
Jun-Jan TRUTH frames), with exactly one change of input population:

  shipped : build_priors(30 pooled Jun-Jan train-split truth frames, lo)
  D1 fix  : build_priors(ALL masked day frames of the scored split, lo_split)

build_priors drops rows with NaN speed/flow, so on masked frames it pools
exactly the split's OBSERVED cells; the global fallback (glob_s / glob_f) is
then the split's own observed-cell mean, and link x slot cells with no
observed cell in the split fall back to it -- the shipped rule end to end.

Link order lo: derived from the split's own first day frame exactly as the
original build derived it from a train day frame
(day.dropna(milepost).drop_duplicates(link_id).sort_values(milepost)).
Cross-checked against the serve-time derivation in build_day_features
(net links sorted by milepost mapped from the day frame); mismatch = STOP.

Feb-2031 is never listed or read: splits iterated are validation/private only.

Usage: build_priors_split.py PANEL SPLIT   (one pair per process)
       build_priors_split.py --merge       (combine per-pair stats)
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

TFB = Path("/home/hatch/workspace/tfb")
sys.path.insert(0, str(TFB / "ops/award_pkg_offbox/scripts"))
sys.path.insert(0, str(TFB / "builds/dl_blitz/tree"))
import lane_io  # noqa: E402
import loaders  # noqa: E402
import t1_features as T  # noqa: E402  (shipped build_priors lives here)

BUILD = TFB / "builds/w57_d1d2_splitfix"
OUT = BUILD / "priors_split"
DATA = TFB / "data/kaggle_public"
PANELS = lane_io.PANELS
SPLITS = ("validation", "private")


def read_masked(path: Path) -> pd.DataFrame:
    """Byte-for-byte the read in infer_w28.read_masked."""
    df = pd.read_parquet(path, columns=[c for c in lane_io.MASKED_COLS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["link_id"] = df["link_id"].astype(str)
    df["station_id"] = df["station_id"].astype(str)
    return df


def link_order_train_style(day: pd.DataFrame) -> list[str]:
    """build_train_w28_scale.py:170-172 derivation."""
    return (day.dropna(subset=["milepost"]).drop_duplicates("link_id")
            .sort_values("milepost")["link_id"].astype(str).tolist())


def link_order_serve_style(panel: str, day: pd.DataFrame) -> list[str]:
    """build_day_features (t1_features.py:64-73) derivation."""
    net = loaders.load_network(panel)
    links = net["links"].copy()
    links["link_id"] = links["link_id"].astype(str)
    mp = day.dropna(subset=["milepost"]).drop_duplicates("link_id").set_index(
        "link_id")["milepost"]
    links["milepost"] = links["link_id"].map(mp)
    links = links.sort_values("milepost").reset_index(drop=True)
    return links["link_id"].tolist()


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def run_pair(panel: str, split: str):
    t0 = time.time()
    shipped = np.load(TFB / "builds/w28_t1_scale/data"
                      / f"priors_scale_{panel}.npz")
    root = DATA / "corridors" / panel / split / "mainline_states_masked"
    files = sorted(root.glob("mask_regime=*/*.parquet"))
    assert files, f"no masked files for {panel}/{split}"
    frames = [read_masked(p) for p in files]
    lo = link_order_train_style(frames[0])
    lo_serve = link_order_serve_style(panel, frames[0])
    assert lo == lo_serve, (
        f"{panel}/{split}: link-order mismatch train-style vs serve-style "
        f"({len(lo)} vs {len(lo_serve)}) -- STOP")
    assert len(lo) == shipped["speed"].shape[0], (
        f"{panel}/{split}: link count {len(lo)} != shipped priors "
        f"{shipped['speed'].shape[0]} -- STOP")

    priors = T.build_priors(frames, lo)

    # reporting extras in one light pass (no big concat): split's own global
    # fallback values + count of (link, slot) cells the fallback had to fill.
    li = {l: i for i, l in enumerate(lo)}
    cnt = np.zeros((len(lo), 288))
    ssum = 0.0
    fsum = 0.0
    nobs = 0
    for day in frames:
        d = day.dropna(subset=["speed_kmh", "flow_vph"])
        ts = pd.to_datetime(d["timestamp"], utc=True)
        slot = (ts.dt.hour * 60 + ts.dt.minute).to_numpy() // 5
        lc = d["link_id"].astype(str).map(li).to_numpy()
        ok = lc >= 0
        np.add.at(cnt, (lc[ok], slot[ok]), 1)
        ssum += float(d["speed_kmh"].to_numpy()[ok].sum())
        fsum += float(d["flow_vph"].to_numpy()[ok].sum())
        nobs += int(ok.sum())
    glob_s = ssum / max(nobs, 1)
    glob_f = fsum / max(nobs, 1)
    n_fallback = int((cnt == 0).sum())

    out_npz = OUT / f"priors_{panel}_{split}.npz"
    np.savez_compressed(out_npz, speed=priors["speed"],
                        flow=priors["flow"], nslot=priors["nslot"])
    ds = np.abs(priors["speed"] - shipped["speed"])
    df_ = np.abs(priors["flow"] - shipped["flow"])
    rec = {
        "panel": panel, "split": split, "n_days": len(files),
        "n_links": len(lo), "n_obs_cells": nobs,
        "glob_s_split": glob_s, "glob_f_split": glob_f,
        "n_fallback_cells": n_fallback,
        "md5": md5_of(out_npz),
        "vs_shipped": {
            "speed_mean_abs_delta": float(ds.mean()),
            "speed_max_abs_delta": float(ds.max()),
            "speed_frac_cells_changed": float((ds > 1e-9).mean()),
            "flow_mean_abs_delta": float(df_.mean()),
            "flow_max_abs_delta": float(df_.max()),
            "flow_frac_cells_changed": float((df_ > 1e-9).mean()),
        },
        "seconds": round(time.time() - t0, 1),
    }
    (BUILD / f"priors_stats_{panel}_{split}.json").write_text(
        json.dumps(rec, indent=2))
    print(f"{panel}/{split}: days={len(files)} links={len(lo)} "
          f"obs={nobs:,} fallback_cells={n_fallback} "
          f"glob=({glob_s:.3f},{glob_f:.1f}) "
          f"dSpeed mean={ds.mean():.4f} max={ds.max():.3f} "
          f"dFlow mean={df_.mean():.2f} max={df_.max():.1f} "
          f"[{rec['seconds']}s]", flush=True)


def merge():
    stats = {}
    for panel in PANELS:
        for split in SPLITS:
            p = BUILD / f"priors_stats_{panel}_{split}.json"
            assert p.exists(), f"missing stats for {panel}/{split}"
            stats[f"{panel}|{split}"] = json.loads(p.read_text())
    (BUILD / "priors_split_stats.json").write_text(json.dumps(stats, indent=2))
    print("WROTE priors_split_stats.json with", len(stats), "pairs")


if __name__ == "__main__":
    if sys.argv[1] == "--merge":
        merge()
    else:
        run_pair(sys.argv[1], sys.argv[2])
