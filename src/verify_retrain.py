"""verify_retrain.py — prediction-equality acceptance for retrained .cbm models.

The award-relevant question after a from-scratch retrain is NOT "do the
.cbm files have identical md5s" (they cannot: CatBoost regenerates a
35-byte save-time UUID on every save_model call — verified 2026-10-12).
It is: "do the retrained models make identical predictions."

For each of the 4 models (speed/flow x s42/s43):
  1. train_meta check (if --meta-dir given): n_train, best_iteration,
     val_RMSE (exact, 16 digits) vs the lane references.
  2. probe check: the same 2000-row probe (fixed seed 20310301) through the
     SHIPPED .cbm and the RETRAINED .cbm -> max|d| must be 0.0 (bit-identical).

Usage:
  python verify_retrain.py --models-dir <dir with 4 retrained .cbm files> [--root ...]

Exit 0 on PASS, 1 on FAIL.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def _resolve_tfb_root(argv):
    for i, a in enumerate(argv):
        if a == "--root" and i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser().resolve()
        if a.startswith("--root="):
            return Path(a.split("=", 1)[1]).expanduser().resolve()
    env = os.environ.get("TFB_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path("/home/hatch/workspace/tfb")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", required=True,
                    help="dir with w28_scale_{speed_kmh,flow_vph}_s{42,43}.cbm")
    ap.add_argument("--meta-dir", default=None,
                    help="dir with train_meta_{speed_kmh,flow_vph}.json "
                         "(default: --models-dir)")
    ap.add_argument("--root", default=None)
    ap.add_argument("--probe-n", type=int, default=2000)
    ap.add_argument("--probe-seed", type=int, default=20310301)
    a = ap.parse_args()

    TFB = _resolve_tfb_root(sys.argv[1:])

    import numpy as np
    import pandas as pd
    from catboost import CatBoostRegressor, Pool

    DATA = TFB / "builds" / "w28_t1_scale" / "data"
    SHIP = TFB / "builds" / "w28_t1_scale" / "models"
    NEW = Path(a.models_dir).expanduser().resolve()
    META = Path(a.meta_dir).expanduser().resolve() if a.meta_dir else NEW

    feat = json.load(open(DATA / "t1_feat_v2_scale.json"))
    ALL_FEATS = feat["features"]
    CAT_COLS = ["panel_cat", "link_gcode", "mask_regime"]
    CAT_IDX = [ALL_FEATS.index(c) for c in CAT_COLS]

    REF_META = {}
    for target, mfile, kdir in (("speed_kmh", "train_meta_speed_kmh.json", "speed"),
                                ("flow_vph", "train_meta_flow_vph.json", "flow")):
        d = json.load(open(TFB / "builds" / "w28_t1_scale" / "kout" / kdir / mfile))
        REF_META.update(d)

    def load_probe(target):
        cols = list(ALL_FEATS) + [target]
        frames = [pd.read_parquet(DATA / f"train_abs_scale_p{i:02d}.parquet",
                                  columns=cols) for i in range(10)]
        data = pd.concat(frames, ignore_index=True)
        del frames
        X = data[ALL_FEATS].copy()
        for c in CAT_COLS:
            X[c] = X[c].astype(np.int64)
        rng = np.random.default_rng(a.probe_seed)
        idx = rng.choice(len(X), size=a.probe_n, replace=False)
        return X.iloc[idx].reset_index(drop=True)

    all_pass = True
    for target in ("speed_kmh", "flow_vph"):
        Xp = load_probe(target)
        pool = Pool(Xp, cat_features=CAT_IDX)
        for seed in (42, 43):
            tag = f"w28_scale_{target}_s{seed}"
            ship_p = SHIP / f"{tag}.cbm"
            new_p = NEW / f"{tag}.cbm"
            assert ship_p.exists(), f"missing shipped model {ship_p}"
            assert new_p.exists(), f"missing retrained model {new_p}"
            meta_p = META / f"train_meta_{target}.json"
            if meta_p.exists():
                meta = json.load(open(meta_p))[tag]
                ref = REF_META[tag]
                meta_ok = (meta["n_train"] == ref["n_train"]
                           and meta["best_iteration"] == ref["best_iteration"]
                           and meta["val_RMSE"] == ref["val_RMSE"])
                print(f"{tag}: train_meta -> "
                      f"{'MATCH' if meta_ok else 'MISMATCH vs ' + repr(ref)}",
                      flush=True)
                all_pass = all_pass and meta_ok
            else:
                print(f"{tag}: train_meta skipped (no {meta_p.name})", flush=True)
            m_ship = CatBoostRegressor()
            m_ship.load_model(str(ship_p))
            m_new = CatBoostRegressor()
            m_new.load_model(str(new_p))
            d = np.abs(m_ship.predict(pool) - m_new.predict(pool))
            pok = d.max() == 0.0
            print(f"{tag}: probe max|d|={d.max():.3e} "
                  f"exact-zero frac={(d == 0).mean():.4f} -> "
                  f"{'BIT-IDENTICAL' if pok else 'DIFFERS'}", flush=True)
            all_pass = all_pass and pok
    print("RETRAIN_ACCEPTANCE:", "PASS" if all_pass else "FAIL", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
