"""D2 J1 emitter driver (gated lane w57).

Runs builds/exp006g/emit_g_j1_private.py's OWN emit_split (frozen J1 model,
frozen thresholds, shipped feature pipeline) -- the only substitution is the
occ_ff table source:

  mode=base -> the emitter's original occ_ff_map (shipped pooled table);
               output must reproduce builds/exp006g/queue_006g_gj1_*.csv
               exactly (pipeline replication check).
  mode=fix  -> occ_ff_map patched to this lane's per-split tables
               (occff_split/occ_ff_by_split.parquet, build_occff_split.py).

Outputs go to this lane's emit_fix/ (base_*, fix_*); the original build dir
is never written. Feb-2031 untouched (splits: validation, private).

Usage: emit_d2.py {base|fix}
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

import lightgbm as lgb
import pandas as pd

TFB = os.path.expanduser("~/workspace/tfb")
BUILD = os.path.join(TFB, "builds/w57_d1d2_splitfix")
BUILD_J = os.path.join(TFB, "builds/exp003j")
ROOT = os.path.join(TFB, "data/kaggle_public")

spec = importlib.util.spec_from_file_location(
    "emit_g_j1_private", os.path.join(TFB, "builds/exp006g",
                                      "emit_g_j1_private.py"))
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


def load_split_maps():
    df = pd.read_parquet(os.path.join(BUILD, "occff_split",
                                      "occ_ff_by_split.parquet"))
    maps = {}
    for (split, panel), g in df.groupby(["split", "panel"]):
        maps[(split, panel)] = dict(zip(g["link_id"].astype(str),
                                        g["occ_ff"].astype(float)))
    return maps


def main(mode):
    t0 = time.time()
    model = lgb.Booster(model_file=os.path.join(BUILD_J, "model_J1.txt"))
    assert model.feature_name() == E.MODEL_FEATURES, "model features changed!"
    thresholds = json.load(open(os.path.join(BUILD_J, "thresholds_J1.json")))
    tau_map = {k: v["tau"] for k, v in thresholds.items()}

    if mode == "fix":
        maps = load_split_maps()
        E._CUR_SPLIT = None

        def occ_ff_map_split(panel):
            return maps[(E._CUR_SPLIT, panel)]

        E.occ_ff_map = occ_ff_map_split

    key = pd.read_csv(os.path.join(ROOT, "submission_key.csv"),
                      usecols=["task", "split", "panel", "timestamp",
                               "window_id", "link_id"], low_memory=False)
    key_q = key[key["task"] == "queue"].copy()
    key_q["timestamp"] = pd.to_datetime(
        key_q["timestamp"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in ("panel", "window_id", "link_id", "split"):
        key_q[c] = key_q[c].astype(str)

    outdir = os.path.join(BUILD, "emit_fix")
    os.makedirs(outdir, exist_ok=True)
    for split in ("validation", "private"):
        if mode == "fix":
            E._CUR_SPLIT = split
        kqs = key_q[key_q["split"] == split]
        final, routes = E.emit_split(split, model, tau_map, kqs)
        assert len(final) == len(kqs), (split, len(final), len(kqs))
        out = os.path.join(outdir, f"queue_{mode}_{split}.csv")
        final.to_csv(out, index=False)
        print(f"WROTE {out}: {len(final):,} rows "
              f"({(time.time()-t0)/60:.1f} min)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
