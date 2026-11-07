"""D2 FIX (gated lane w57): rebuild J1 occ_ff PER SCORED SPLIT.

Identical rule to builds/exp003j/build_occff.py:

  occ_ff[panel, link] = median( occupancy | masked speed > 0.85 * vf(link) )
  over masked-layer cells, min_samples = 25,

with exactly the fix's two changes (IDENTIFIABILITY_MAP.md §7, D2):
  1. population: ALL masked days of the scored split itself
     (corridors/{panel}/{split}/mainline_states_masked), not the 16 sampled
     Jun-Jan train days;
  2. fallback: a link with < 25 free-flow samples in the split falls back to
     the POOLED Jun-Jan value for that (panel, link) from the shipped
     occ_ff.parquet (md5 c01eca74823278dbd2742d21738d949e) -- NOT the panel
     median the train build used.

vf comes from exp003j/common.load_fd (fd_parameters.csv), identical source.
Feb-2031 never listed or read.

Usage: build_occff_split.py PANEL SPLIT | --merge
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.expanduser("~/workspace/tfb/builds/exp003j"))
from common import ROOT, load_fd  # noqa: E402  (shipped vf source)

BUILD = os.path.expanduser("~/workspace/tfb/builds/w57_d1d2_splitfix")
OUT = os.path.join(BUILD, "occff_split")
MIN_SAMPLES = 25
PANELS = ["D7_I10_E", "D7_I10_W", "D7_I210_E", "D7_I210_W", "D7_I405_N",
          "D7_I405_S", "D12_I5_N", "D12_I5_S", "D12_I405_N", "D12_I405_S"]
SPLITS = ("validation", "private")
SHIPPED_MD5 = "c01eca74823278dbd2742d21738d949e"


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def run_pair(panel, split):
    t0 = time.time()
    shipped_path = os.path.expanduser(
        "~/workspace/tfb/builds/exp003j/datasets/occ_ff.parquet")
    assert md5_of(shipped_path) == SHIPPED_MD5, "shipped occ_ff md5 drifted"
    shipped = pd.read_parquet(shipped_path)
    pooled = dict(zip(
        shipped[shipped["panel"] == panel]["link_id"].astype(str),
        shipped[shipped["panel"] == panel]["occ_ff"].astype(float)))

    fd = load_fd(panel)
    vf = (0.85 * fd["free_speed_kmh"]).to_dict()
    vf = {str(k): float(v) for k, v in vf.items()}

    pat = os.path.join(ROOT, "corridors", panel, split,
                       "mainline_states_masked", "mask_regime=*",
                       "synthetic_mainline_*.parquet")
    files = sorted(glob.glob(pat))
    assert files, f"no masked files for {panel}/{split}"
    acc = {}
    for f in files:
        df = pd.read_parquet(f, columns=["link_id", "speed_kmh", "occupancy"])
        df = df.dropna(subset=["speed_kmh", "occupancy"])
        df = df[df["link_id"].isin(vf)]
        if df.empty:
            continue
        thr = df["link_id"].map(vf)
        ff = df[df["speed_kmh"] > thr]
        for l, g in ff.groupby("link_id"):
            acc.setdefault(str(l), []).append(g["occupancy"].to_numpy())
    rows = []
    n_fb = 0
    for l in sorted(vf):
        chunks = acc.get(l, [])
        v = np.concatenate(chunks) if chunks else np.array([])
        if len(v) >= MIN_SAMPLES:
            rows.append((panel, l, float(np.median(v)), int(len(v)), "split"))
        else:
            assert l in pooled, (
                f"{panel}/{split}: link {l} has < {MIN_SAMPLES} FF samples "
                f"in split AND no pooled value -- STOP")
            rows.append((panel, l, pooled[l], int(len(v)), "pooled_fallback"))
            n_fb += 1
    out = pd.DataFrame(rows, columns=["panel", "link_id", "occ_ff", "n",
                                      "source"])
    out_path = os.path.join(OUT, f"occ_ff_{panel}_{split}.parquet")
    out.to_parquet(out_path, index=False)

    both = out.set_index("link_id")["occ_ff"]
    ship = pd.Series(pooled)
    common = both.index.intersection(ship.index)
    d = (both[common] - ship[common]).abs()
    rec = {
        "panel": panel, "split": split, "n_days": len(files),
        "n_links": int(len(out)), "n_fallback_links": n_fb,
        "md5": md5_of(out_path),
        "vs_shipped": {
            "mean_abs_delta": float(d.mean()),
            "max_abs_delta": float(d.max()),
            "n_links_changed_gt_1e-9": int((d > 1e-9).sum()),
            "frac_links_changed": float((d > 1e-9).mean()),
        },
        "files": [os.path.basename(f) for f in files],
        "seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(BUILD, f"occff_stats_{panel}_{split}.json"),
              "w") as fh:
        json.dump(rec, fh, indent=2)
    print(f"{panel}/{split}: days={len(files)} links={len(out)} "
          f"fallback={n_fb} dOcc mean={d.mean():.5f} max={d.max():.4f} "
          f"changed={int((d > 1e-9).sum())}/{len(common)} "
          f"[{rec['seconds']}s]", flush=True)


def merge():
    frames = []
    prov = {"rule": "median(occupancy | masked_speed > 0.85*vf)",
            "min_samples": MIN_SAMPLES,
            "population": "all masked days of the scored split",
            "fallback": "pooled Jun-Jan occ_ff value per (panel, link)",
            "pairs": {}}
    for split in SPLITS:
        for panel in PANELS:
            p = os.path.join(BUILD, f"occff_stats_{panel}_{split}.json")
            assert os.path.exists(p), f"missing stats {panel}/{split}"
            rec = json.load(open(p))
            prov["pairs"][f"{panel}|{split}"] = rec
            frames.append(pd.read_parquet(
                os.path.join(OUT, f"occ_ff_{panel}_{split}.parquet")))
            frames[-1]["split"] = split
    all_df = pd.concat(frames, ignore_index=True)
    out_path = os.path.join(OUT, "occ_ff_by_split.parquet")
    all_df.to_parquet(out_path, index=False)
    prov["combined_md5"] = md5_of(out_path)
    prov["combined_rows"] = int(len(all_df))
    with open(os.path.join(OUT, "occ_ff_split_provenance.json"), "w") as fh:
        json.dump(prov, fh, indent=2)
    print(f"WROTE occ_ff_by_split.parquet: {len(all_df)} rows, "
          f"md5 {prov['combined_md5']}")


if __name__ == "__main__":
    if sys.argv[1] == "--merge":
        merge()
    else:
        run_pair(sys.argv[1], sys.argv[2])
