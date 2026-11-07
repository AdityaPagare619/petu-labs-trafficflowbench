"""W28 Lane A kernel training: {TARGET} x seeds 42,43 (W27 abs_full recipe verbatim).

Reads private dataset tfb-w28-scale (train_abs_scale_p00..p09.parquet +
t1_feat_v2_scale.json). Mirrors train_abs_full_flow.py exactly:
  target = {TARGET} (absolute), weight = 1, features = 98 census,
  CatBoost depth 8 lr 0.05 l2 3.0, RMSE, cap 1500, early-stop 100,
  eval split n//20 via default_rng(seed), thread_count 2, use_best_model.
Writes /kaggle/working/: w28_scale_{TARGET}_s{{42,43}}.cbm + train_meta.json.
Feb never touched (shards are Jun-Jan only).
"""
from __future__ import annotations

import gc
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "flow_vph"
SEEDS = (42, 43)
MAX_ITER = 1500
DSDIR = Path("/kaggle/input/datasets/adityapaagare/tfb-w28-scale")
WORK = Path("/kaggle/working")

try:
    import catboost
    from catboost import CatBoostRegressor, Pool
except ImportError as e:
    raise SystemExit(f"catboost unavailable in kernel image: {e}")


def rss_mb():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def main():
    print(f"catboost {catboost.__version__}", flush=True)
    # Integrity: verify shard md5s against shard_md5.txt (with attach-race retries)
    md5_path = DSDIR / "shard_md5.txt"
    for attempt in range(12):
        if md5_path.exists():
            break
        print(f"waiting for dataset attach, attempt {attempt}, "
              f"dir={sorted(p.name for p in DSDIR.glob('*'))}", flush=True)
        time.sleep(10)
    md5ok = 0
    for line in open(md5_path):
        h, name, rows = line.split()
        p = DSDIR / name
        d = hashlib.md5()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                d.update(chunk)
        assert d.hexdigest() == h, f"md5 MISMATCH {name}"
        md5ok += 1
    print(f"shard md5 verified: {md5ok} shards", flush=True)

    feat = json.load(open(DSDIR / "t1_feat_v2_scale.json"))
    all_feats = feat["features"]
    cat_cols = ["panel_cat", "link_gcode", "mask_regime"]
    cat_idx = [all_feats.index(c) for c in cat_cols]
    cols = list(all_feats) + [TARGET]
    frames = []
    for i in range(10):
        frames.append(pd.read_parquet(DSDIR / f"train_abs_scale_p{i:02d}.parquet",
                                      columns=cols))
    data = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    print(f"loaded {data.shape} rss_MB={round(rss_mb())}", flush=True)
    target = data[TARGET].to_numpy()
    X = data[all_feats].copy()
    del data
    gc.collect()
    for c in cat_cols:
        X[c] = X[c].astype(np.int64)
    n = len(X)
    meta = {}
    for seed in SEEDS:
        tag = f"w28_scale_{TARGET}_s{seed}"
        rng = np.random.default_rng(seed)
        eval_idx = rng.choice(n, size=max(1, n // 20), replace=False)
        tr_idx = np.setdiff1d(np.arange(n), eval_idx)
        weight = np.ones(n)
        tr = Pool(X.iloc[tr_idx], label=target[tr_idx], weight=weight[tr_idx],
                  cat_features=cat_idx)
        ev = Pool(X.iloc[eval_idx], label=target[eval_idx],
                  weight=weight[eval_idx], cat_features=cat_idx)
        print(f"{tag} pools n_train={len(tr_idx)} rss_MB={round(rss_mb())}", flush=True)
        m = CatBoostRegressor(loss_function="RMSE", depth=8, learning_rate=0.05,
                              iterations=MAX_ITER, l2_leaf_reg=3.0,
                              random_seed=seed, thread_count=2,
                              early_stopping_rounds=100, verbose=0)
        t0 = time.time()
        m.fit(tr, eval_set=ev, use_best_model=True)
        m.save_model(str(WORK / (tag + ".cbm")))
        meta[tag] = {"n_train": int(len(tr_idx)),
                     "best_iteration": int(m.get_best_iteration()),
                     "val_RMSE": float(m.get_best_score()["validation"]["RMSE"]),
                     "elapsed_s": round(time.time() - t0, 1),
                     "peak_rss_MB": round(rss_mb()),
                     "target": TARGET, "seed": seed}
        print(tag, json.dumps(meta[tag]), flush=True)
        del tr, ev, m
        gc.collect()
    (WORK / f"train_meta_{TARGET}.json").write_text(json.dumps(meta, indent=1))
    print("DONE", TARGET, flush=True)


if __name__ == "__main__":
    main()
