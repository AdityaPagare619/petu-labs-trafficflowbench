"""D1 inference driver (gated lane w57).

Replicates infer_w28.run_valpriv's loop EXACTLY, importing the shipped
per-day machinery (load_models, read_masked, load_ramps_day_split,
predict_day) from ops/award_pkg_offbox/scripts/infer_w28.py -- models,
feature pipeline, ensemble rule, fallback and emitter are the shipped code.

The ONLY differences vs run_valpriv:
  * priors source: mode=base -> shipped pooled priors (replication check);
                   mode=fix  -> per-split priors built by build_priors_split.py
  * output dir: this lane's cand_states_{base,fix}/.

Usage: infer_d1.py {base|fix} PANEL   (both splits for that panel)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

TFB = Path("/home/hatch/workspace/tfb")
sys.path.insert(0, str(TFB / "ops/award_pkg_offbox/scripts"))
import infer_w28 as I  # noqa: E402  (shipped serve path)
import lane_io  # noqa: E402
import loaders  # noqa: E402

BUILD = TFB / "builds/w57_d1d2_splitfix"
DATA = TFB / "data/kaggle_public"
PANELS = lane_io.PANELS


def load_priors_split(panel: str, split: str):
    pr = np.load(BUILD / "priors_split" / f"priors_{panel}_{split}.npz")
    return {"speed": pr["speed"], "flow": pr["flow"], "nslot": int(pr["nslot"])}


def run(mode: str, only_panel: str):
    outdir = BUILD / f"cand_states_{mode}"
    outdir.mkdir(exist_ok=True)
    ms, mf = I.load_models()
    for split in ("validation", "private"):
        for pi, panel in enumerate(PANELS):
            if panel != only_panel:
                continue
            out_csv = outdir / f"cand_state_{split}_{panel}.csv"
            if out_csv.exists():
                print(f"skip (done): {out_csv.name}", flush=True)
                continue
            t0 = time.time()
            net = loaders.load_network(panel)
            priors = (I.load_priors(panel) if mode == "base"
                      else load_priors_split(panel, split))
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
                    day = I.read_masked(path)
                    rd = I.load_ramps_day_split(panel, date, split)
                    keys, ps, pf = I.predict_day(day, net, rd, priors, pi,
                                                 ms, mf)
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
            allpred = pd.concat(rows, ignore_index=True)
            merged = template.merge(
                allpred, on=["timestamp", "station_id", "link_id",
                             "mask_regime"],
                how="left", validate="one_to_one")
            miss = int(merged["speed_kmh"].isna().sum())
            print(f"{mode} {split}/{panel}: days={n_days} "
                  f"template_rows={len(template)} unmatched={miss} "
                  f"t={time.time()-t0:.0f}s", flush=True)
            assert miss == 0, f"{split}/{panel}: {miss} template rows unmatched"
            merged.to_csv(out_csv, index=False)
            print(f"  wrote {out_csv.name}", flush=True)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
