"""W34-B Stage B acceptance: prediction-equality of retrained vs shipped .cbm models.

For each of the 4 models (speed/flow x s42/s43):
  1. train_meta check: n_train, best_iteration, val_RMSE (16 digits) vs
     builds/w28_t1_scale/kout/{speed,flow}/train_meta_{speed_kmh,flow_vph}.json
  2. probe check: same 2000-row probe (fixed seed) through shipped .cbm and
     retrained .cbm -> max|d| must be 0.0 (bit-identical).

File md5 is NOT checked (CatBoost save-time UUID — documented caveat).
"""
import json
import os
import sys
from pathlib import Path


def _resolve_tfb_root():
    """Workspace root (pure stdlib). Precedence: --root CLI arg > TFB_ROOT env > legacy default."""
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


TFB = _resolve_tfb_root()

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
DATA = TFB / "builds" / "w28_t1_scale" / "data"
MODELS = TFB / "builds" / "w28_t1_scale" / "models"
KOUT = TFB / "ops" / "award_pkg" / "kout_{target}_full"
PROBE_SEED = 20310301
PROBE_N = 2000

feat = json.load(open(DATA / "t1_feat_v2_scale.json"))
ALL_FEATS = feat["features"]
CAT_COLS = ["panel_cat", "link_gcode", "mask_regime"]
CAT_IDX = [ALL_FEATS.index(c) for c in CAT_COLS]

REF_META = {}
for target, mfile in (("speed_kmh", "train_meta_speed_kmh.json"),
                      ("flow_vph", "train_meta_flow_vph.json")):
    d = json.load(open(TFB / "builds" / "w28_t1_scale" / "kout" /
                       ("speed" if target == "speed_kmh" else "flow") / mfile))
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
    rng = np.random.default_rng(PROBE_SEED)
    idx = rng.choice(len(X), size=PROBE_N, replace=False)
    return X.iloc[idx].reset_index(drop=True)


def main():
    all_pass = True
    for target in ("speed_kmh", "flow_vph"):
        Xp = load_probe(target)
        pool = Pool(Xp, cat_features=CAT_IDX)
        for seed in (42, 43):
            tag = f"w28_scale_{target}_s{seed}"
            retrain_dir = Path(str(KOUT).format(
                target="speed" if target == "speed_kmh" else "flow"))
            meta = json.load(open(retrain_dir / f"train_meta_{target}.json"))[tag]
            ref = REF_META[tag]
            meta_ok = (meta["n_train"] == ref["n_train"]
                       and meta["best_iteration"] == ref["best_iteration"]
                       and meta["val_RMSE"] == ref["val_RMSE"])
            print(f"{tag}: train_meta n_train={meta['n_train']} "
                  f"best_iter={meta['best_iteration']} "
                  f"val_RMSE={meta['val_RMSE']!r} -> "
                  f"{'MATCH' if meta_ok else 'MISMATCH vs ref ' + repr(ref)}")
            if not meta_ok:
                all_pass = False
            m_ship = CatBoostRegressor()
            m_ship.load_model(str(MODELS / f"{tag}.cbm"))
            m_new = CatBoostRegressor()
            m_new.load_model(str(retrain_dir / f"{tag}.cbm"))
            ps = m_ship.predict(pool)
            pn = m_new.predict(pool)
            d = np.abs(ps - pn)
            pok = d.max() == 0.0
            print(f"{tag}: probe max|d|={d.max():.3e} "
                  f"exact-zero frac={(d == 0).mean():.4f} -> "
                  f"{'BIT-IDENTICAL' if pok else 'DIFFERS'}")
            if not pok:
                all_pass = False
    print("STAGE_B_ACCEPTANCE:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
