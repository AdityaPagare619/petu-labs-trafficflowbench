"""Merge the W28 candidate submission: production 006G+J1 with ONLY the T1
(state) leg replaced by the W28 scale-ensemble predictions.

Faithful adaptation of ../w27_bundle_gates/merge_candidate.py (same key
order, same queue/odme code paths) with state_path pointed at the W28
candidate state files and the output renamed. Queue + odme values therefore
come from the identical code and sources as production; verify_diff.py proves
byte-level equality of every non-state row.
"""
import gc
import time
from pathlib import Path

import numpy as np
import pandas as pd

TFB = Path.home() / "workspace" / "tfb"
DATA = TFB / "data" / "kaggle_public"
SUB = TFB / "submissions"

PANELS_T1 = ["D12_I405_N", "D12_I405_S", "D12_I5_N", "D12_I5_S", "D7_I10_E",
             "D7_I10_W", "D7_I210_E", "D7_I210_W", "D7_I405_N", "D7_I405_S"]
SPLITS = ("validation", "private")
OUT_NAME = "submission_w28_scale_v1.csv"


def state_path(split, panel):
    return (TFB / "builds" / "w28_scale_bundle_gates" / "cand_states"
            / f"cand_state_{split}_{panel}.csv")


def queue_path(split):
    return TFB / "builds" / "exp006g" / f"queue_006g_gj1_{split}.csv"


def main():
    t0 = time.time()
    print("loading key (slim)...", flush=True)
    key = pd.read_csv(
        DATA / "submission_key.csv",
        usecols=["submission_id", "task", "split", "panel", "timestamp",
                 "station_id", "link_id", "window_id", "departure_time",
                 "path_id"],
        dtype={"task": str, "split": str, "panel": str, "timestamp": str,
               "station_id": str, "link_id": str, "window_id": str,
               "departure_time": str, "path_id": str})
    key["submission_id"] = key["submission_id"].astype(np.int64)
    n = len(key)
    print(f"key: {n:,} rows", flush=True)
    assert n == 6980503, f"key row count {n} != 6,980,503"

    speed = np.zeros(n)
    flow = np.zeros(n)
    qpred = np.zeros(n)
    pflow = np.zeros(n)

    for split in SPLITS:
        for panel in PANELS_T1:
            pos = np.flatnonzero(
                (key["task"] == "state").to_numpy() &
                (key["split"] == split).to_numpy() &
                (key["panel"] == panel).to_numpy())
            ks = key.iloc[pos][["timestamp", "station_id", "link_id"]]
            st = pd.read_csv(
                state_path(split, panel),
                usecols=["timestamp", "station_id", "link_id",
                         "speed_kmh", "flow_vph"],
                dtype={"timestamp": str, "station_id": str, "link_id": str})
            m = ks.merge(st, on=["timestamp", "station_id", "link_id"],
                         how="left", indicator=True)
            nm = int((m["_merge"] == "both").sum())
            assert nm == len(ks), f"{split}/{panel}: {len(ks)-nm} unmatched"
            sv = m["speed_kmh"].to_numpy(dtype=float)
            fv = m["flow_vph"].to_numpy(dtype=float)
            assert np.isfinite(sv).all() and np.isfinite(fv).all()
            assert (sv >= 0).all() and (fv >= 0).all()
            speed[pos] = sv
            flow[pos] = fv
            del ks, st, m, sv, fv
            gc.collect()
        print(f"  state/{split} done ({(time.time()-t0)/60:.1f} min)", flush=True)

    for split in SPLITS:
        q = pd.read_csv(queue_path(split),
                        dtype={"split": str, "panel": str,
                               "window_id": str, "timestamp": str,
                               "link_id": str})
        q["queue_pred"] = q["queue_pred"].astype(np.int64)
        pos = np.flatnonzero(
            (key["task"] == "queue").to_numpy() &
            (key["split"] == split).to_numpy())
        kq = key.iloc[pos][["panel", "window_id", "timestamp", "link_id"]]
        m = kq.merge(q, on=["panel", "window_id", "timestamp", "link_id"],
                     how="left", indicator=True)
        nm = int((m["_merge"] == "both").sum())
        assert nm == len(kq), f"queue/{split}: {len(kq)-nm} unmatched"
        qp = m["queue_pred"].to_numpy(dtype=float)
        assert set(np.unique(qp)).issubset({0.0, 1.0}), \
            f"queue_pred not binary: {np.unique(qp)[:5]}"
        qpred[pos] = qp
        del q, kq, m, qp
        gc.collect()
    print(f"  queue done ({(time.time()-t0)/60:.1f} min)", flush=True)

    od = pd.read_csv(TFB / "exp001" / "odme_all.csv",
                     usecols=["panel", "departure_time", "path_id", "path_flow"],
                     dtype={"panel": str, "departure_time": str,
                            "path_id": str})
    pos = np.flatnonzero((key["task"] == "odme").to_numpy())
    ko = key.iloc[pos][["panel", "departure_time", "path_id"]]
    m = ko.merge(od, on=["panel", "departure_time", "path_id"],
                 how="left", indicator=True)
    nm = int((m["_merge"] == "both").sum())
    assert nm == len(ko), f"odme: {len(ko)-nm} unmatched"
    pf = m["path_flow"].to_numpy(dtype=float)
    assert np.isfinite(pf).all() and (pf >= 0).all()
    pflow[pos] = pf
    del od, ko, m, pf
    gc.collect()
    print(f"  odme done ({(time.time()-t0)/60:.1f} min)", flush=True)

    out = pd.DataFrame({
        "submission_id": key["submission_id"].to_numpy(),
        "task": key["task"].to_numpy(),
        "speed_kmh": speed,
        "flow_vph": flow,
        "queue_pred": qpred,
        "path_flow": pflow,
    })
    del key, speed, flow, qpred, pflow
    gc.collect()
    out_path = SUB / OUT_NAME
    out.to_csv(out_path, index=False)
    print(f"WROTE {out_path}: {len(out):,} rows "
          f"({(time.time()-t0)/60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
