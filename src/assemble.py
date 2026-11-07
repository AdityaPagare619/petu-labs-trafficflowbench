"""ASSEMBLY + VALIDATION + G-7 ROW-DIFF (gated lane w57) -- memory-lean v2.

Candidate = parent bundle (ref 57369480, submission_w54_onset_v1.csv,
md5 f596f2089403c552f38fd6bd0f9808a8) with EXACTLY two component-level
changes and nothing else:

  D1: state rows' (speed_kmh, flow_vph) taken from the per-split-priors
      inference (cand_states_fix/), after proving cand_states_base/
      reproduces the parent's state rows numerically on every row.
  D2: queue_pred of ONGOING-window rows taken from the per-split occ_ff
      J1 run (emit_fix/queue_fix_*.csv), after proving the base J1 run
      reproduces builds/exp006g/queue_006g_gj1_*.csv exactly and the
      parent's ongoing rows equal that base run. Onset rows untouched.

Staged so peak memory stays low on this 7GB box:
  stage_tables(): per (panel, split) merges -> aligned npz value tables.
  main(): vector ops on parent arrays; untouched-component proofs; schema
          validation; candidate write; row_diff_report.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

TFB = Path("/home/hatch/workspace/tfb")
BUILD = TFB / "builds/w57_d1d2_splitfix"
PARENT = TFB / "submissions/submission_w54_onset_v1.csv"
PARENT_MD5 = "f596f2089403c552f38fd6bd0f9808a8"
DATA = TFB / "data/kaggle_public"
PANELS = ["D7_I10_E", "D7_I10_W", "D7_I210_E", "D7_I210_W", "D7_I405_N",
          "D7_I405_S", "D12_I5_N", "D12_I5_S", "D12_I405_N", "D12_I405_S"]
SPLITS = ("validation", "private")
OUT = BUILD / "candidate_submission_w57_d1d2.csv"
TDIR = BUILD / "state_tables"
TDIR.mkdir(exist_ok=True)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def load_key():
    key = pd.read_csv(DATA / "submission_key.csv",
                      usecols=["submission_id", "task", "split", "panel",
                               "timestamp", "station_id", "link_id",
                               "mask_regime", "window_id"],
                      low_memory=False)
    key["timestamp"] = pd.to_datetime(
        key["timestamp"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in ("panel", "station_id", "link_id", "mask_regime", "window_id",
              "split", "task"):
        key[c] = key[c].astype(str)
    key = key.sort_values("submission_id").reset_index(drop=True)
    assert (key["submission_id"].to_numpy()
            == np.arange(1, len(key) + 1)).all(), "key ids not 1..N in order"
    return key


def stage_tables(key):
    """Per (panel, split): align base/fix cand_state values to key positions."""
    done = TDIR / "DONE"
    if done.exists():
        return
    state_mask = (key["task"] == "state").to_numpy()
    kstate = key[state_mask]
    pos_all = np.flatnonzero(state_mask)
    for split in SPLITS:
        for panel in PANELS:
            ks = kstate[(kstate["split"] == split)
                        & (kstate["panel"] == panel)]
            pos = pos_all[(kstate["split"] == split).to_numpy()
                          & (kstate["panel"] == panel).to_numpy()]
            assert len(ks) == len(pos)
            for mode in ("base", "fix"):
                df = pd.read_csv(
                    BUILD / f"cand_states_{mode}"
                    / f"cand_state_{split}_{panel}.csv",
                    dtype={"timestamp": str, "station_id": str,
                           "link_id": str, "mask_regime": str})
                m = ks.merge(df, on=["timestamp", "station_id", "link_id",
                                     "mask_regime"], how="left",
                             validate="one_to_one")
                assert len(m) == len(ks) and m["speed_kmh"].notna().all(), \
                    f"cand coverage incomplete {mode} {panel} {split} -- STOP"
                m = m.sort_values("submission_id")
                assert (m["submission_id"].to_numpy()
                        == ks.sort_values("submission_id")["submission_id"]
                        .to_numpy()).all()
                np.savez(TDIR / f"{mode}_{panel}_{split}.npz",
                         pos=pos[np.argsort(
                             ks["submission_id"].to_numpy())],
                         speed=m["speed_kmh"].to_numpy(),
                         flow=m["flow_vph"].to_numpy())
                del df, m
            print(f"tables {panel}/{split} done", flush=True)
    done.write_text("ok")


def gather(mode, n_rows):
    speed = np.full(n_rows, np.nan)
    flow = np.full(n_rows, np.nan)
    for split in SPLITS:
        for panel in PANELS:
            z = np.load(TDIR / f"{mode}_{panel}_{split}.npz")
            speed[z["pos"]] = z["speed"]
            flow[z["pos"]] = z["flow"]
    return speed, flow


def main():
    report = {}
    assert md5_of(PARENT) == PARENT_MD5, "parent bundle md5 drifted -- STOP"
    key = load_key()
    stage_tables(key)
    n = len(key)
    state_mask = (key["task"] == "state").to_numpy()
    queue_mask = (key["task"] == "queue").to_numpy()
    odme_mask = (key["task"] == "odme").to_numpy()
    del key
    import gc
    gc.collect()

    parent = pd.read_csv(PARENT)
    assert len(parent) == 6_980_503 == n
    assert (parent["submission_id"].to_numpy()
            == np.arange(1, n + 1)).all(), "parent ids not 1..N in order"

    # ---------------- D1 ----------------
    pv_s = parent.loc[state_mask, "speed_kmh"].to_numpy()
    pv_f = parent.loc[state_mask, "flow_vph"].to_numpy()
    b_s_full, b_f_full = gather("base", n)
    f_s_full, f_f_full = gather("fix", n)
    b_s, b_f = b_s_full[state_mask], b_f_full[state_mask]
    f_s, f_f = f_s_full[state_mask], f_f_full[state_mask]
    assert not (np.isnan(b_s).any() or np.isnan(f_s).any()), \
        "state tables do not cover every state row -- STOP"
    del b_s_full, b_f_full, f_s_full, f_f_full
    gc.collect()
    base_repro = {
        "speed_max_abs_err": float(np.abs(b_s - pv_s).max()),
        "flow_max_abs_err": float(np.abs(b_f - pv_f).max()),
        "speed_n_inexact": int((b_s != pv_s).sum()),
        "flow_n_inexact": int((b_f != pv_f).sum()),
    }
    report["D1_base_replication_vs_parent"] = base_repro
    assert base_repro["speed_max_abs_err"] < 1e-6, "base != parent (speed)"
    assert base_repro["flow_max_abs_err"] < 1e-3, "base != parent (flow)"
    del b_s, b_f
    gc.collect()
    report["D1_row_diff"] = {
        "state_rows": int(state_mask.sum()),
        "speed_rows_changed": int((f_s != pv_s).sum()),
        "flow_rows_changed": int((f_f != pv_f).sum()),
        "rows_changed_either": int(((f_s != pv_s) | (f_f != pv_f)).sum()),
        "speed_delta_mean_abs": float(np.abs(f_s - pv_s).mean()),
        "speed_delta_max_abs": float(np.abs(f_s - pv_s).max()),
        "flow_delta_mean_abs": float(np.abs(f_f - pv_f).mean()),
        "flow_delta_max_abs": float(np.abs(f_f - pv_f).max()),
    }
    cand_s = parent["speed_kmh"].to_numpy().copy()
    cand_f = parent["flow_vph"].to_numpy().copy()
    cand_s[state_mask] = f_s
    cand_f[state_mask] = f_f
    del f_s, f_f, pv_s, pv_f
    gc.collect()

    # ---------------- D2 ----------------
    key2 = load_key()
    kq = key2[queue_mask]
    for split in SPLITS:
        mine = pd.read_csv(BUILD / "emit_fix" / f"queue_base_{split}.csv")
        ship = pd.read_csv(TFB / "builds/exp006g"
                           / f"queue_006g_gj1_{split}.csv")
        assert len(mine) == len(ship) == 87_000
        mm = mine.merge(ship, on=["split", "panel", "window_id", "timestamp",
                                  "link_id"], suffixes=("_mine", "_ship"),
                        validate="one_to_one")
        assert len(mm) == 87_000
        n_diff = int((mm["queue_pred_mine"] != mm["queue_pred_ship"]).sum())
        report[f"D2_base_replication_{split}"] = {
            "rows": 87_000, "queue_pred_diffs_vs_shipped_emitter": n_diff}
        assert n_diff == 0, f"base J1 run != shipped emitter on {split}"
        del mine, ship, mm
    ongoing = set()
    for split in SPLITS:
        for panel in sorted(set(kq["panel"])):
            wi = pd.read_csv(DATA / "task2" / panel / split
                             / "window_index.csv")
            for w in wi.itertuples(index=False):
                if str(w.condition) == "queue_ongoing":
                    ongoing.add((split, panel, str(w.window_id)))
    ong = np.array([(s, p, w) in ongoing for s, p, w in
                    zip(kq["split"], kq["panel"], kq["window_id"])])
    old_q = parent.loc[queue_mask, "queue_pred"].to_numpy()

    def queue_values(fname_tpl):
        frames = []
        for s in SPLITS:
            d = pd.read_csv(BUILD / "emit_fix" / (fname_tpl % s))
            for c in ("panel", "window_id", "link_id", "split"):
                d[c] = d[c].astype(str)
            frames.append(d)
        allq = pd.concat(frames, ignore_index=True)
        m = kq.merge(allq, on=["split", "panel", "window_id", "timestamp",
                               "link_id"], how="left", validate="one_to_one")
        assert len(m) == len(kq) and m["queue_pred"].notna().all()
        mm = m.set_index("submission_id").loc[kq["submission_id"].to_numpy()]
        return mm["queue_pred"].to_numpy(dtype=float)

    base_q = queue_values("queue_base_%s.csv")
    fix_q = queue_values("queue_fix_%s.csv")
    del key2, kq
    gc.collect()
    report["D2_bundle_base_agreement"] = {
        "ongoing_rows_base_vs_parent_diffs": int((base_q[ong] != old_q[ong])
                                                  .sum()),
        "onset_rows_base_vs_parent_diffs": int((base_q[~ong] != old_q[~ong])
                                                .sum()),
        "note": "onset diffs expected: parent onset = W54-A leg, base = 006G",
    }
    assert (base_q[ong] == old_q[ong]).all(), \
        "parent ongoing rows != base J1 run -- STOP"
    new_q = old_q.copy()
    new_q[ong] = fix_q[ong]
    flips = new_q != old_q
    report["D2_row_diff"] = {
        "queue_rows": int(queue_mask.sum()),
        "ongoing_rows": int(ong.sum()),
        "onset_rows": int((~ong).sum()),
        "flips_total": int(flips.sum()),
        "flips_0_to_1": int(((old_q == 0) & (new_q == 1)).sum()),
        "flips_1_to_0": int(((old_q == 1) & (new_q == 0)).sum()),
        "onset_rows_changed": int((flips & ~ong).sum()),
    }
    assert report["D2_row_diff"]["onset_rows_changed"] == 0

    # ---------------- assemble + untouched proofs ----------------
    cand = parent
    cand["speed_kmh"] = cand_s
    cand["flow_vph"] = cand_f
    qcol = cand["queue_pred"].to_numpy().copy()
    qcol[queue_mask] = new_q
    cand["queue_pred"] = qcol
    del cand_s, cand_f, qcol, new_q, old_q, base_q, fix_q
    gc.collect()
    # untouched proofs need parent arrays: reload the three untouched cols
    par_q = pd.read_csv(PARENT, usecols=["queue_pred", "path_flow",
                                         "speed_kmh", "flow_vph"])
    report["untouched"] = {
        "odme_rows": int(odme_mask.sum()),
        "odme_path_flow_diffs": int(
            (cand.loc[odme_mask, "path_flow"].to_numpy()
             != par_q.loc[odme_mask, "path_flow"].to_numpy()).sum()),
        "state_queue_pred_diffs": int(
            (cand.loc[state_mask, "queue_pred"].to_numpy()
             != par_q.loc[state_mask, "queue_pred"].to_numpy()).sum()),
        "state_path_flow_diffs": int(
            (cand.loc[state_mask, "path_flow"].to_numpy()
             != par_q.loc[state_mask, "path_flow"].to_numpy()).sum()),
        "queue_speed_diffs": int(
            (cand.loc[queue_mask, "speed_kmh"].to_numpy()
             != par_q.loc[queue_mask, "speed_kmh"].to_numpy()).sum()),
        "queue_flow_diffs": int(
            (cand.loc[queue_mask, "flow_vph"].to_numpy()
             != par_q.loc[queue_mask, "flow_vph"].to_numpy()).sum()),
        "queue_path_flow_diffs": int(
            (cand.loc[queue_mask, "path_flow"].to_numpy()
             != par_q.loc[queue_mask, "path_flow"].to_numpy()).sum()),
    }
    del par_q
    gc.collect()
    assert all(v == 0 for k, v in report["untouched"].items()
               if k.endswith("diffs"))

    # ---------------- schema validation ----------------
    val = {}
    val["rows"] = int(len(cand))
    val["ids_1_to_N_in_order"] = bool(
        (cand["submission_id"].to_numpy() == np.arange(1, len(cand) + 1)).all())
    val["duplicate_ids"] = int(cand["submission_id"].duplicated().sum())
    val["nulls_total"] = int(cand.isna().sum().sum())
    val["queue_pred_values"] = sorted(cand["queue_pred"].unique().tolist())
    pf = cand["path_flow"].to_numpy(dtype=float)
    val["path_flow_finite"] = bool(np.isfinite(pf).all())
    val["path_flow_min"] = float(pf.min())
    sp = cand["speed_kmh"].to_numpy(dtype=float)
    fl = cand["flow_vph"].to_numpy(dtype=float)
    val["speed_finite"] = bool(np.isfinite(sp).all())
    val["flow_finite"] = bool(np.isfinite(fl).all())
    val["speed_min"] = float(sp.min())
    val["flow_min"] = float(fl.min())
    report["schema_validation"] = val
    assert val["rows"] == 6_980_503 and val["ids_1_to_N_in_order"]
    assert val["duplicate_ids"] == 0 and val["nulls_total"] == 0
    assert set(val["queue_pred_values"]) <= {0.0, 1.0}
    assert val["path_flow_finite"] and val["path_flow_min"] >= 0
    assert val["speed_finite"] and val["flow_finite"]

    cand.to_csv(OUT, index=False)
    report["candidate"] = {"path": str(OUT), "md5": md5_of(OUT),
                           "parent_md5": PARENT_MD5}
    (BUILD / "row_diff_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
