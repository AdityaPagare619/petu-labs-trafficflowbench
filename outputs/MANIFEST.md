# Outputs — top-2 submissions

GitHub rejects files over 100 MB in git, and each submission is ~404 MB uncompressed (~140 MB gzipped). The two files therefore ship as **release assets** on the [v1.0 release](../../releases/tag/v1.0), not in the git tree. Their identities are pinned here by md5.

## 1 — Certified floor (highest)

| | |
|---|---|
| File | `submission_w57_d1d2_v1.csv` (gzipped as `submission_w57_d1d2_v1.csv.gz`) |
| Kaggle ref | `57429904` |
| Public score | **0.85330** (20 Oct 2026) |
| Rows | 6,980,503 (6,735,795 state / 174,000 queue / 70,708 ODME) |
| md5 (uncompressed) | `e6db2a22a5e676955ab225358c0e378c` |
| md5 (gzipped asset) | see `submission_w57_d1d2_v1.csv.gz.md5` in the release |
| Composition | 0.84994 parent + exactly two changes (W57 D1/D2 split-fidelity fixes), certified by audit W58-L1 |

## 2 — Floor parent (second highest)

| | |
|---|---|
| File | `submission_w54_onset_v1.csv` (gzipped as `submission_w54_onset_v1.csv.gz`) |
| Kaggle ref | `57369480` |
| Public score | 0.84994 (19 Oct 2026) |
| Rows | 6,980,503 |
| md5 (uncompressed) | `f596f2089403c552f38fd6bd0f9808a8` |
| md5 (gzipped asset) | see `submission_w54_onset_v1.csv.gz.md5` in the release |
| Composition | W54-C T4 own-counts refit + W54-A onset leg on the W28 production base |

## Verification

```bash
# After downloading and gunzipping:
md5sum submission_w57_d1d2_v1.csv   # e6db2a22a5e676955ab225358c0e378c
md5sum submission_w54_onset_v1.csv  # f596f2089403c552f38fd6bd0f9808a8
```

The floor is also reproducible from raw inputs via `scripts/reproduce-final.sh` (prediction-equality acceptance; the assembly re-run reproduces the floor file md5-identically).
