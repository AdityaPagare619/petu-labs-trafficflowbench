# Data

## Coverage

- **Panels:** 10 motorway panels — D7_I10, D7_I210, D7_I405, D12_I5, D12_I405, each direction (N/S, E/W).
- **Resolution:** 5-minute mainline state observations (speed km/h, flow vph/lane).
- **Training months available:** June 2030 – January 2031 (8 months).
- **Validation month (public):** March 2031. **Hidden month (private):** April 2031.
- **February 2031:** sealed selection month — opened exactly once per experiment under a pre-registered frozen protocol (hashes recorded before opening, no post-open tuning). Never used for fitting.
- **Road graph:** link lengths, lane counts, topology (used for T3/T4 and the ODME operator A).
- **Submission key:** 6,980,503 rows (6,735,795 state / 174,000 queue / 70,708 ODME).

## Masking census

Observed masking is approximately **20/30/50% per regime**. Training augmentation reproduces that census exactly (978,619 natural rows + augmentation = 3,725,267 rows in 10 shards).

## Features (v2 set, `src/t1_features_v2.py`)

- **Episode/wave features:** congestion-wave and episode structure around each cell, exposing spatiotemporal context on the 5-minute grid.
- **Pooled priors** (`priors_scale_{panel}.npz`): empirical per-(link, 5-minute slot) mean speed and flow — deterministic sum/count accumulators from 30 days pooled across the eight training months. Frozen inputs, regenerable from released data.
- Masked-observation statistics, link geometry (length, lanes), time-of-day/calendar encodings.
- **J1 (T2) features (28):** `step`, `q_age_x_step`, `tod_sin`/`tod_cos`, `k_ratio_up`, `ds_min`, `q_ext_up`, occupancy, dissipation precursors — see `models/model_J1.txt` header.

## Training recipe (W28 scale)

- Four CatBoost regressors: speed/flow × seeds {42, 43}. Depth 8, learning rate 0.05, up to 1500 iterations, `l2_leaf_reg` 3.0, early stopping on a 5% seed-deterministic validation split.
- Trained on private Kaggle kernels from the on-Kaggle dataset `adityapaagare/tfb-w28-scale` (10/10 shard md5s verified in-kernel before training).
- Ensemble prediction = mean of the two seeds per target.
- Retrain refresh (6 Nov 2026): all four models retrained from scratch with prediction-equality acceptance — `train_meta` identical to 16 digits, 2000-row probe predictions bit-identical (max|Δ| = 0.0).

## What is NOT in this repo

- The competition's raw data (not ours to redistribute). Get it from the Kaggle competition page.
- February 2031 data — sealed, never touched, never included.
- No external dataset, pretrained model, or paid API was used anywhere in the pipeline.
