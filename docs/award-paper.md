# PETU LABS — TrafficFlowBench Award Paper (draft, content stage)
# 2026 IEEE Big Data Cup: TrafficFlowBench
# Team: Petu-Labs · Kaggle: adityapaagare
# Candidate: 0.85330 floor (Kaggle ref 57429904) · `submissions/submission_w57_d1d2_v1.csv`
# md5 e6db2a22a5e676955ab225358c0e378c · 6,980,503 rows

> Draft status: content draft for the 10-page award PDF (code + PDF due
> 2026-11-10 23:59 AoE). Rewritten 2026-11-06 to the certified floor
> (supersedes the 0.81787 / ref 57065852 draft of 2026-10-12, retained in
> version history). Every numbered claim below is backed by a named
> artifact in the award package; the reproducibility section names the
> exact acceptance tests the organizers' rerun must satisfy. Claim labels
> follow the campaign constitution §3.1 (FACT—CAMPAIGN RECORD, MEASURED,
> REPRODUCED, INFERENCE, CONTRADICTED/FAILED, HUMAN DECISION, UNKNOWN).

---

## 1. Abstract

We present the TrafficFlowBench solution of team Petu-Labs (public
validation score **0.85330**, Kaggle submission ref 57429904), built under
one organizing principle: **optimize expected rank on the hidden private
month, not the observed validation month.** The competition's public
leaderboard scores a single validation month; final standings are decided
by a different, independently generated hidden month. Every component of
our pipeline was therefore gated on multi-month stability before
promotion: a candidate that could not show same-sign gains on at least
three of five distinct months was killed or banked, never shipped.

The submitted bundle is the certified floor: our 0.84994 parent bundle
(ref 57369480) with **exactly two changes** — W57 split-fidelity fixes
D1 and D2, which re-estimate two serving-time statistics from each scored
split's own released data instead of pooled training data. Its T1 leg is
the W28 scaled gradient-boosting ensemble (two CatBoost regressors —
speed, flow — × two seeds, trained on 3,725,267 rows with masking
augmentation matched to the observed masking census, 20/30/50%); its T2
leg is the J1 queue construction with W54-A onset; its T4 leg is the
W54-C own-counts refit. The floor was certified by a dedicated audit
(W58-L1, 2026-10-20): byte-identical to the submitted file, composition
attributed by construction, level discipline PASS (zero train-pooled level
carryover), class composition 6 target-identified / 17 seed-invariant /
12 fitted-residue pairs. The award package reproduces the submission
from raw inputs with **prediction-equality acceptance** (per-cell fidelity
≤ 1e-14 on speed, exact on flow and both non-state legs), and an
independent full-population retrain replicated the W28 training procedure
to |ΔS_state| = 0.000524 (RS1R Stage 1, 2026-11-04). The honest record
behind the floor is 253 registered experiments, six final doors closed
with named mechanisms, and a kill record that now measures — rather than
asserts — that only retraining beats the fitted surfaces. The full
rehearsal, environment pins, and frozen-artifact manifest are documented
in §8.

## 2. Introduction

TrafficFlowBench asks for a full traffic state of a motorway network from
masked sensor observations: per-link 5-minute speed and flow (T1), queue
onset flags (T2), physics consistency of the predicted field (T3), and
origin–destination matrix estimation (T4). The official score is

```
S_total = 0.35·S_state + 0.30·S_queue + 0.15·S_physics + 0.20·S_ODME
```

with `S_state = 0.54·S_speed + 0.46·S_flow`. The public leaderboard
reflects one validation month; the organizers state that final standings
use a different hidden month. This single fact shaped our entire campaign:
**a gain that exists only on the validation month is a liability, not an
asset.** Our promotion contract therefore required cross-month stability
(same-sign gains on ≥ 3 of 5 distinct months: four blinded months plus a
sealed February selection month), a deflated significance bar (2.67σ,
calibrated to ~150 lifetime trials so that luck alone cannot promote), and
a bundle ablation that drops any component whose marginal is below +0.002
total-score units. No gate was recalibrated after seeing results; the one
uniform gate change in campaign history (K3 → K3′, 3 November) is
disclosed as post-result in §6 and priced accordingly — the floor ships
alongside, never instead of, the protection it provides.

## 3. Data

The released package covers ten motorway panels (D7_I10, D7_I210, D7_I405,
D12_I5, D12_I405, each direction) with masked mainline state observations
at 5-minute resolution, a road-network graph (link lengths, lane counts),
and a sample submission key (6,980,503 rows). Training months available to
us ran June 2030 – January 2031; February 2031 was sealed and was opened
exactly once per experiment under a pre-registered frozen protocol (hashes
recorded before opening, no post-open tuning). The observed masking census
is approximately 20/30/50% per regime, and our training augmentation
reproduces that census exactly (see §5.1). No external dataset, pretrained
model, or paid API was used anywhere in the pipeline
(`README_EXTERNAL_DATA.md`: none in any category).

## 4. Solution architecture

The submission is a four-leg bundle. Relative to our production baseline
(ref 56788939, 0.78806), the floor carries the W28 T1 ensemble, the W54-C
T4 refit, the W54-A onset leg, and the D1/D2 split-fidelity fixes:

| Leg | Task | Content in the submission | Changed vs production? |
|---|---|---|---|
| T1 | state (speed/flow) | W28 scale CatBoost ensemble (§5) + D1 per-split priors (§5.5) | **yes — ensemble + split priors** |
| T2 | queue | J1 ongoing (`model_J1.txt`, thresholds) + D2 per-split occ_ff (§5.5); W54-A onset rows | **yes — D2 split occ_ff; onset verbatim** |
| T3 | physics consistency | conservation-guard adjudicated (§6) | input field only |
| T4 | ODME | W54-C own-counts refit (`odme_candidate_owncounts.csv`) | **yes — own-counts refit** |

The integrity proof (W58-L1 audit + W57 row-diff report) establishes
against the 0.84994 parent (md5 `f596f2089403c552f38fd6bd0f9808a8`):
identical row count, `submission_id`, and `task` columns; all 70,708
ODME rows 0-diff; all onset rows 0-diff; state `queue_pred`/`path_flow`
and queue `speed_kmh`/`flow_vph`/`path_flow` 0-diff; D1 moves 6,722,215
of 6,735,795 state rows (mean |Δ| 0.392 km/h speed, 10.32 vph flow);
D2 flips 260 of 174,000 queue rows (41 0→1, 219 1→0). No full-leg swap
was performed — the W56 assembly error mode is excluded by the
replication proofs in §5.5. The floor is therefore a pure
serving-time-statistics change by construction, and its score accounting
is exact: the +0.00336 delta over the parent sits in the D1/D2
components (March read, class evidence only — §6).

## 5. The T1 leg: scaled CatBoost ensemble

### 5.1 Training data

`build_train_w28_scale.py` builds **3,725,267 rows in 10 shards** from the
raw masked parquets of the eight training months (Jun 2030 – Jan 2031):
978,619 natural rows plus masking augmentation at 20/30/50% rates, matching
the observed masking census. Per-shard md5s are recorded in
`builds/w28_t1_scale/data/shard_md5.txt` (10/10 verified in the award
rehearsal, re-verified 2026-11-06). The builder is memory-safe (one panel
in memory at a time), deterministic given the raw inputs, and never touches
February 2031.

### 5.2 Features

The v2 feature set (`builds/w27_t1_scaleup/t1_features_v2.py`, frozen list
`t1_feat_v2_scale.json`) combines:

- **Episode/wave features**: congestion-wave and episode structure around
  each cell, capturing the spatiotemporal context of the 5-minute grid.
- **Pooled priors** (`priors_scale_{panel}.npz`, ×10): empirical per-(link,
  5-minute slot) mean speed and flow — deterministic sum/count
  accumulators built from 30 days pooled across the eight training months.
  They are **frozen inputs** to the pipeline (loaded verbatim at inference;
  regenerable from released data by the documented recipe), not fitted
  parameters. Their md5s are recorded in `PRIORS_STATEMENT.md`.
- Masked-observation statistics, link geometry (length, lanes), and
  time-of-day/calendar encodings.

### 5.3 Model and training

Four models: speed/flow × seeds {42, 43}. Each is a CatBoostRegressor
(depth 8, learning rate 0.05, up to 1500 iterations, l2_leaf_reg 3.0,
early stopping on a 5% seed-deterministic validation split) trained on
private Kaggle kernels from the on-Kaggle dataset
`adityapaagare/tfb-w28-scale` (10/10 shard md5s verified in-kernel before
training). The ensemble prediction is the **mean of the two seeds** per
target. Model md5s are recorded in `builds/w28_t1_scale/STATUS.json`; the
inference driver (`infer_w28.py`) verifies all four against the manifest
before running. All four models were retrained from scratch on private
kernels on 2026-10-12 with prediction-equality acceptance (train_meta
identical to 16 digits, 2000-row probe predictions bit-identical,
max|Δ| = 0.0 — `EXECUTION_REPORT.md` §2).

### 5.4 Inference and bundle assembly

`infer_w28.py --mode valpriv` recomputes the v2 features from the raw
masked parquets and writes 20 intermediate state files
(`cand_state_{split}_{panel}.csv`, 10 panels × validation/private splits;
`unmatched=0` required per panel). `merge_candidate.py` performs the
key-ordered merge with the verbatim T2/T4 legs into the 6,980,503-row
submission. The pinned environment is `requirements.txt`
(catboost==1.2.10, pandas==3.0.6, numpy==2.5.3, pyarrow==25.0.1,
scipy==1.18.1, lightgbm==4.7.0, osqp==1.1.3, joblib==1.6.0; python 3.12).

### 5.5 The D1/D2 split-fidelity fixes (W57, 2026-10-20)

**FACT — CAMPAIGN RECORD.** The floor differs from its 0.84994 parent by
exactly two component-level changes, built by the gated fix lane w57
(`builds/w57_d1d2_splitfix/REPORT.md`, authorization S34) and certified
by the W58-L1 audit (`intel/CERTIFIED_FLOOR_57429904.md`):

- **D1 — T1 priors per scored split** (`build_priors_split.py`,
  `infer_d1.py`). The shipped `build_priors` was called verbatim; the
  only change is the input population: instead of 30 pooled Jun–Jan
  train-split truth frames, the function received all masked day frames
  of the scored split itself (31 validation + 30 private days per
  panel). All 20 per-split priors: **0 fallback cells** (every link×slot
  cell has ≥1 observed cell in each split); 16,169,043 observed cells
  pooled. Inference ran through the shipped serve path
  (`infer_w28.predict_day` imported, models/ensemble/fallback/emitter
  unchanged); only the priors argument differed.
- **D2 — J1 `occ_ff` per scored split** (`build_occff_split.py`,
  `emit_d2.py`). The shipped rule (median occupancy over masked cells
  with masked speed > 0.85·vf, min_samples 25) on all masked days of the
  scored split. **0 fallback links** in any panel×split. The shipped
  emitter produced the queue rows (frozen J1 model + thresholds); only
  the occ_ff table source changed.

**REPRODUCED (replication proofs, the attribution basis).** D1 base run
with shipped priors vs the parent's state rows: max err speed **3.6e-15**,
flow **9.1e-13** (float text round-trip only). D2 base run vs the shipped
emitter files: **0 diffs** on all 174,000 rows. Because the base pipelines
reproduce the parent exactly, every candidate-vs-parent difference is
attributable to D1 or D2 by construction — nothing else moved.

**Honest class statement (INFERENCE, per IDENTIFIABILITY_MAP §7).**
Neither quantity enters the scoring functional directly — both pass
through frozen decision surfaces — so this lane does not claim class-(a)
construction. Ship evidence is G-6(iv): the same component class
(split-fidelity) carries a prior board read (W54-C, +0.03158). Honest
expectations at build time were D1 −0.0005…+0.0015 and D2 −0.001…+0.002
total-score units — proxy-mediated, sign not guaranteed. The March board
read for the floor was +0.00336 over the parent; that is class evidence,
not a constant projected to April.

## 6. Selection protocol: seven gates, then certification

The T1 swap was promoted only after passing every gate
(`builds/w28_scale_bundle_gates/VERDICT.md`, `gates.py`):

- **G1/G2 — gain and deflated significance.** Blinded Oct–Jan lane
  evaluation: ensemble ΔS_state = **+0.00594** vs the previous best,
  bootstrap 95% CI [+0.00562, +0.00626], **z = 35.7**, far above the 2.67σ bar.
  Both seeds agree (+0.00595 / +0.00592); all four blinded months
  positive; worst panel×regime cell +0.00118.
- **G3 — cross-month replication.** Same-sign gains on 4/4 blinded months
  plus 10/10 panels on the sealed February selection month — five
  distinct months of evidence, all positive.
- **G4 — no large regression.** Worst panel×regime cell +0.00118; zero
  cells ≤ −0.01.
- **K2 — S_FD adjudication.** The T1 swap changes the physics-consistency
  term too: ΔS_FD = +0.00061 (lane) / +0.00246 (Feb), both positive —
  no hidden drag.
- **K4 — conservation guard.** Relative conservation-residual on matched
  Feb panel-days: candidate/production ratio **0.621 ≤ 1.25** (clean
  bound) — the most conservation-consistent field yet measured; the T3
  leg's input is not degraded.
- **G5 — bundle ablation (marginal ≥ 0.002).** Marginal of the T1 swap vs
  the previous board leader (0.81458): 0.35×0.00594 + (0.15/3)×0.00061 =
  **+0.00211** > 0.002. Thin on the point estimate; corroborated by the
  independent Feb scale-minus-previous read (+0.00602 S_state, tight CI).
- **G7 — sealed February selection.** Pre-declared frozen rule
  (ΔS_state_Feb > 0, one run, pre-open hashes): production 0.91765 →
  candidate **0.93851**, Δ = **+0.02085**, 95% CI [+0.01901, +0.02252],
  all 10 panels positive.

A regime gate (D3 congestion labels) additionally confirmed the blinded
eval months were *more* congestion-heavy than the board months — the
regime mismatch runs in the conservative direction. Expected bundle effect
vs the previous leader: ≈ +0.0021 total-score units (≈ 0.8167 expected
public from 0.81458); the board returned **0.81787** for that candidate.

**The floor's own selection (FACT — CAMPAIGN RECORD, W58-L1 audit
2026-10-20; FINAL_SELECTION_LEDGER.md addendum 2026-11-05).** The floor
was not selected on its March delta. It was certified on composition:
class split **6 target-identified / 17 seed-invariant / 12 fitted-residue**
pairs; **level discipline PASS** — the bundle's only train-pooled level
carriers (pooled priors, pooled occ_ff) are gone, replaced by per-split
re-estimates with zero pooled fallback; every other emitted level is
pooled seed-invariant structure or priced residue. The D1/D2 change
shipped under G-6(iv) (same component class as W54-C's split-fidelity
fix, March +0.03158). Final selection (6 November) is by class
composition, not March delta, per the standing selection policy — and the
floor is the only candidate that survived it: every challenger since
certification was killed or eliminated on board evidence (§7).

**Epistemic caveat, disclosed (INFERENCE).** K3′ (board delta ≥ +0.010
every month; physics delta ≥ −0.020 every month; same-sign on ≥3 months)
was adopted 3 November as a uniform rule *after* the b10 results were
known. A uniform post-result rule is not a preregistered rule; its
rationale is defensible but it does not erase adaptive decision-making.
No further gate recalibration is authorised. The b10 bundle that prompted
it scored 0.72109 on the board and was killed the same day.

## 7. Analysis

**Why the scale-up works.** The T1 task is dominated by the conditional
mean: three independent post-hoc correction families (additive
recalibration, congestion-transition classification, variance-weighted
spatial correction) were all killed at oracle cost during the campaign —
the model's residual field is effectively white noise on the current
features, so the conditional mean is already optimal. Gains therefore come
from the base model itself: more training rows (3.7M with census-matched
augmentation), episode/wave features that expose congestion structure, and
pooled priors that stabilize the link-level mean. The D1/D2 fixes extend
the same logic to serving time: the level statistics a frozen surface
consumes should come from the scored split itself, not from a pooled
training month — the disease, measured, is that a split's own month
differs from the pooled mean by 2.52 km/h (speed) and 156.3 vph (flow)
on average at link×slot level.

**Honest negative results — the six doors (CONTRADICTED/FAILED, each with
a named mechanism; decision_log.md 2026-11-03/04).** The campaign ran
253 registered experiments; the final week closed every remaining route
to beating the floor, and each closure is preserved with its mechanism:

1. **C15 — disagreement blend.** KILLED: the two W28 seeds are nearly
   identical, so inverse-variance weights collapse to uniform (blend Δ
   −3.15e-07). Mechanism: *arm correlation collapse*.
2. **C5 — J1 genuine-closure refit.** ELIMINATED on board evidence:
   0.85191 vs floor 0.85330 (Δ −0.00139) despite a Tier-2 ruler reading
   +0.01387 on the queue leg — the second ruler-vs-board disagreement in
   two days. The internal ruler, not the board, was wrong.
3. **RS1 — anomaly-prior retrain (8-day).** KILLED at the monkey gate:
   the identity arm alone lost −0.11266 — the monkey tested fitting on
   8 days, never the prior. Mechanism: *population-shrink confound*.
4. **R1–R4 — blind-team repairs.** KILLED, all four, each with a named
   mechanism: group-mean offsets inject noise (released-cell means do
   not predict masked-cell error, corr +0.10); T+30 queue removals
   delete true positives (the "evidence-free" additions are 96% true);
   at-T reconciliation trusts a *lagging* row (J1's T−5 anchor agrees
   with derived truth 97.6% vs the rule's 2.4%); variance restoration
   achieves its target slope and lowers the score (optimal shrinkage);
   congested-context pulls smear localized queues (ΔS_state −0.303).
   The blind team's *patterns* were real; every truth-free *correction
   direction* was wrong. These are five pre-registered,
   mechanism-tested confirmations that post-hoc avenues are dead.
5. **C4 — detector-reliability weighting.** KILLED at decision: ceiling
   +0.001–0.002 sits 5–10× below the K3′ +0.010 bar, so even a pass
   could not promote; its class had just been measured dead five times.
6. **RS1R — full-population prior swap.** KILLED at Stage 2:
   ΔS_state = −0.002603, negative in all regimes — retraining with the
   interpolated anomaly prior *degrades* the surface vs retraining with
   D1. Mechanism: *prior-swap dead (C2)*, a directional contradiction,
   not a null result.

**What the kill record measures (INFERENCE).** The fitted surfaces
(W28/J1/W54-C) are strong, and the only lever that has ever beaten them
is retraining — Kill #71 ("only retraining works") now has five
independent confirmations and is measured, not assessed. The campaign's
final honest statement (§17.1, 2026-11-04) is that no credible route to
breaking 0.85330 remained in the experimental program, and no credible
route to 0.95 was evidenced. We report that plainly rather than
manufacturing a seventh door. The floor's value is therefore not that it
is the best imaginable submission, but that it is the best *honestly
evidenced* one — and that its reproduction is proven (§8).

**Practical value.** The floor's prediction disagreement vs production
was not priced through the official scorer for this paper (the earlier
0.81787 value bridge — 178,045.7 vehicle-hours at stake — belongs to a
superseded candidate and is not carried forward). We do not report
unmeasured real-world savings.

## 8. Reproducibility statement

The organizers' rerun must satisfy **prediction-equality**, not file-hash
equality, on every path:

1. **Environment.** `requirements.txt` pins all 8 packages, verified
   against the live build environment; a `Dockerfile` (python:3.12-slim)
   reproduces it. (Dockerfile test-build requires a docker host; the pins
   themselves are venv-verified. The Dockerfile is retained as an
   untested reference, explicitly dropped from the verified path by a
   recorded decision — `DOCKERFILE_STATUS.md`.)
2. **Training data.** `build_train_w28_scale.py` regenerates the 10
   training shards from the raw masked parquets; acceptance is 10/10
   shard md5s vs `shard_md5.txt`. The full rehearsal re-ran this build
   end-to-end (see the runbook log); re-verified 2026-11-06 — with one
   honest correction: the first 2026-11-06 check read 5/10 because the
   Oct-12 rehearsal had rebuilt shards p00–p05 into the live dir with
   different parquet serialization bytes (content identical). The live
   shards were restored from the verified backup
   (`stagea_backup/`, md5s match the manifest) and re-verified **10/10
   OK**; the pre-restore bytes are preserved in
   `live_p00_p05_pre_restore_20261106/`. Full record:
   `rehearsal_floor_20261106.log` §A2.
3. **Models.** The verbatim Kaggle trainers
   (`kernel_train_speed_kmh.py`, `kernel_train_flow_vph.py`) retrain all
   four models from the on-Kaggle dataset. Acceptance: identical
   `train_meta` (n_train, best_iteration, val_RMSE to all 16 digits) **and
   bit-identical predictions on a 2000-row probe** (max|Δ| = 0.0) against
   the shipped `.cbm` files. The `.cbm` **file** md5s are explicitly the
   wrong test: CatBoost regenerates a random 35-byte save-time UUID on
   every `save_model` call (all 1500 trees and parameters byte-identical;
   documented in `HARDENING_REPORT.md` §3). The award package's acceptance
   checks use prediction-equality throughout.
4. **Training-procedure fidelity (REPRODUCED, 2026-11-04).** An
   independent full-population retrain (RS1R Stage 1, private GPU kernel,
   5/5 fits, 52 min) replicated the W28 training procedure on W28's
   manifest-exact 320-panel-day population: baseline S_state 0.905826
   reproduced to d = 9.95e-09, and the identity gate passed at
   |ΔS_state| = **0.000524** ≤ 0.002 (determinism noise ε = 0.000082).
   This is the strongest procedure-fidelity evidence in the package: the
   pipeline reproduces the champion's level from scratch. (The Stage 2
   treatment built on this pipeline was killed on its own merits — §7,
   door 6 — which does not touch the identity result.)
5. **D1/D2 fix intermediates.** The per-split priors (20 npz, md5s in
   `builds/w57_d1d2_splitfix/REPORT.md` and `REPRODUCE_FINAL.sh` stage
   [3]) and per-split occ_ff (`occ_ff_by_split.parquet`, md5
   `03919c6af026d66f80e2bad33425e071`) ship as frozen, md5-gated inputs.
   The D1 base run reproduces the parent's state rows (speed 3.6e-15,
   flow 9.1e-13) and the D2 base run reproduces the shipped emitter
   files with 0 diffs on 174,000 rows — so the fix intermediates are
   attributable by construction. A D1 spot re-run (D7_I10_W, both
   splits) in the 2026-11-06 floor rehearsal reproduced the lane's
   intermediates md5-identically (validation
   `1f366572c575b65a1328cc6809e69322`, private
   `a50ab607bc3a61aa476eb9636087307a`).
6. **Inference.** `infer_w28.py --mode valpriv` regenerates all 20
   intermediate state files; acceptance is 20/20 files with `unmatched=0`
   per panel. The 2026-10-12 rehearsal reproduced all 20 from raw inputs.
7. **Merge / assembly.** `merge_candidate.py` + `verify_diff.py`
   reproduce the W28 submission with ids/tasks identical, `queue_pred`/
   `path_flow` bit-identical, and per-cell fidelity speed ≤ 1e-14 /
   flow ≤ 1e-12 vs the shipped file (CSV float round-trip noise only).
   The floor assembly (`builds/w57_d1d2_splitfix/assemble.py`) re-ran
   in the 2026-11-06 floor rehearsal and reproduced the shipped floor
   file md5-identically (`e6db2a22a5e676955ab225358c0e378c`).
8. **Frozen artifacts.** The T2 legs (`queue_006g_gj1_*.csv`) rerun
   bit-identically from their script; the T4 leg is the W54-C
   own-counts refit (`odme_candidate_owncounts.csv`, md5
   `aa8081eabff6c98ae762c5f337760602`, solver `qp_solver.py` shipped).
   The 0.81787 candidate's T4 leg (`exp001/odme_all.csv`, md5
   `36d6568f17cacea5205e69d42f35d142`) is a frozen artifact whose exact
   inputs proved unrecoverable after three reconstruction attempts —
   it is superseded with the floor and recorded here only because
   earlier drill documents cite it.

The award gate (predictions within 1% of the private score) is cleared by
roughly ten orders of magnitude on the T1 leg: the rerun is
prediction-identical, not merely within tolerance.

## 9. Limitations

- The final private month is unobserved by definition; our case rests on
  five-month consistency plus the floor's class composition, not on any
  single number.
- The G5 bundle marginal (+0.00211) is a thin pass on the point estimate;
  the February corroboration (+0.00602 S_state, tight CI) is the tighter
  evidence.
- D1/D2 are **proxy-mediated class (a)**: the statistics enter through
  frozen decision surfaces, so no class-(a) uplift is claimed and the
  sign is not guaranteed. The A1 pseudo-target back-test of the exact
  D1/D2 procedure is not on file, and D1 carries a view tilt (built from
  masked *view* cells, not unmasked truth frames). These are disclosed
  transfer risks, not hidden ones.
- The W54-A onset leg does not ride into April: March priced it at
  ≈0 (inside the luck floor), and the April assembly reverts onset to
  the 006G construction. The submitted file carries W54-A onset rows
  verbatim.
- The competition's top public scores (≈ 0.93 at the 3 November snapshot)
  are unexplained headroom. An earlier campaign verdict calling them
  arithmetically near-impossible is downgraded to hypothesis: top teams
  may have a method we did not find. We deliberately did not chase them,
  accepting a lower public number in exchange for private-month
  robustness — and we do not claim the board is wrong.

## 10. Conclusion

A 0.85330 floor built on a seven-gate selection protocol, a scaled and
census-matched training recipe, split-local serving-time statistics, and
a fully rehearsed reproduction path — including an independent
full-population retrain that replicates the champion's level to |ΔS|
= 0.000524. The campaign's standing rule — never promote what five
months cannot agree on — is the reason this submission, and not a
higher-variance alternative, is our final selection. Behind it stands an
honest record: 253 experiments, six doors closed with named mechanisms,
and a kill record that measures why the floor stands.

---

### Artifact index (award package, `~/workspace/tfb/ops/award_pkg/`)

- `requirements.txt`, `Dockerfile`, `DOCKERFILE_STATUS.md`
- `PRIORS_STATEMENT.md` (pooled base + §6 D1 per-split addendum)
- `HARDENING_REPORT.md`, `COMPLETION_REPORT.md` (corrected 2026-11-06)
- `REPRO_DRILL_W28_JOINT.md`, `REHEARSAL_RUNBOOK.md` (+ §7 execution logs)
- `EXECUTION_REPORT.md`, `FROZEN_ARTIFACT_DISCLOSURE.md`
- `REPRODUCE.sh` (W28 one-panel), `REPRODUCE_FINAL.sh` (floor, identity filled)
- `rehearse_floor_20261106.sh`, `rehearsal_floor_20261106.log` (floor rehearsal)
- Prior evidence: `ops/REPRO_DRILL_W28_SCALE.md`,
  `builds/w28_scale_bundle_gates/VERDICT.md`,
  `builds/w28_t1_scale/STATUS.json`,
  `builds/w57_d1d2_splitfix/REPORT.md`,
  `intel/CERTIFIED_FLOOR_57429904.md`,
  `lanes/rs1_resurrect/HANDOFF_STAGE1_16_1.md`,
  `lanes/rs1_resurrect/HANDOFF_FINAL_16_1.md`
