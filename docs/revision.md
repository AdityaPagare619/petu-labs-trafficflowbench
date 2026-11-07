# REVISION — Architecture & Code Approaches, First Data → Floor
## Principal revision by Petu, hands-on from raw artifacts (not subagent summaries)

**Order:** Aditya, 6 Nov ~23:57 IST — "revise the checkpoints and improve perfectly... instead of taking subagents' suggestions, learn from what they went through." Video session ~12:00 IST Sat 7 Nov.
**Method:** I read the raw artifacts myself — arena REPORT_B + REPORT_C in full, synthesis HANDOFF_SYNTH_16.1, Breakthrough-Max README, Argon VERDICTs, award PDF draft, floor certification, decision log (grep-verified), and the registration thread live from Gmail (6 Nov 23:59 IST). Every number below names its source. The night-stack team (lanes/night_stack/) runs in parallel and is untouched by this revision.

---

## 1. Architecture evolution — checkpoint by checkpoint (23 board reads, verified)

The ladder is **23 scored campaign reads**, not 15 (Arena-1), not 18 (lane a), not 21 (my own 23:20 count). The 010F A/B pair (refs 56814979/56815009) was missed because the decision-log grep pattern `ref 5…` does not match the plural `refs 56814979/56815009`. Lesson recorded: grep both `ref ` and `refs ` forms. Aditya's own random test (ref 56768673, 0.55343) is excluded from campaign tracking per his order.

| # | Date | Checkpoint | Ref | Score | What changed / verdict |
|---|---|---|---|---|---|
| 1 | 30 Sep | EXP-001 | 56702693 | 0.55343 | start |
| 2 | 1 Oct | EXP-002E+003C | 56749658 | 0.67689 | new best |
| 3 | 1 Oct | EXP-002E+003E | 56751176 | 0.69821 | new best |
| 4 | 2 Oct | EXP-003 | 56754078 | 0.72285 | new best |
| 5 | 2 Oct | EXP-003J | 56757681 | 0.72502 | J1 queue construction begins |
| 6 | 2 Oct | BUNDLE-005D | 56777096 | 0.77217 | first bundle |
| 7 | 3 Oct | BUNDLE-006GK | 56788939 | 0.78806 | **production baseline (006G+J1)** |
| 8 | 4 Oct | 009B-SHIP | 56803574 | 0.73461 | rejected — first ship lesson |
| 9 | 4 Oct | 010F arm A | 56814979 | 0.78806 | reproduction of production, exact |
| 10 | 4 Oct | 010F arm B | 56815009 | 0.78960 | ΔLB +0.00154, BANKED (3× below G1 bar) |
| 11 | 6 Oct | W17-LANE1 | 56878315 | 0.76971 | rejected (−0.01835) |
| 12 | 7 Oct | W23 | 56900351 | 0.69960 | rejected (−0.08846); backfilled-onset error |
| 13 | 10 Oct | W27 | 57043897 | 0.81458 | new best |
| 14 | 11 Oct | W28-JOINT | 57061691 | 0.81530 | new best |
| 15 | 11 Oct | W28-SCALE | 57065852 | 0.81787 | **T1 scale ensemble — the floor's T1 leg** |
| 16 | 19 Oct | W54-C | 57367435 | 0.84945 | **biggest single win (+0.03158); T4 own-counts QP refit, NOT a fitted model** |
| 17 | 19 Oct | floor parent (W54-A onset) | 57369480 | 0.84994 | floor parent; onset leg |
| 18 | 20 Oct | W56-L1-TROW | 57409088 | 0.84714 | rejected (−0.0028); assembly error (reverted onset leg) |
| 19 | 20 Oct | **W57-D1D2 = FLOOR** | **57429904** | **0.85330** | **certified floor; D1/D2 split-fidelity fixes** |
| 20 | 28 Oct | L1 MAIN | 57732941 | 0.85282 | below floor |
| 21 | 28 Oct | L1 PARALLEL | 57732984 | 0.85142 | below floor |
| 22 | 3 Nov | S61/b10 | 57934521 | 0.72109 | **KILLED (−0.13221); means lose to dynamics** |
| 23 | 4 Nov | C5/W59-N1 | 57961316 | 0.85191 | **ELIMINATED (−0.00139); ruler-vs-board inversion #2** |

**Standing now:** floor 0.85330; #1 Max Pollard 0.93124 (gap +0.07794); to 0.95 +0.09670; rank ~393 (Aditya's report, passive drift). **Every candidate read since the floor (4 reads: the Oct-28 pair, S61, C5) has failed.** The floor has not been displaced since 20 Oct.

**Architecture as it stands (the floor's composition, certified W58-L1):**
- T1: W28 scale CatBoost ensemble — speed/flow × seeds {42, 43}, depth 8, lr 0.05, ≤1500 iters, trained on 3,725,267 rows (978,619 natural + masking augmentation at 20/30/50% matching the observed census), 10 shards, private Kaggle kernels. Ensemble = mean of two seeds per target.
- T2: J1 (LightGBM text, 634 trees × 63 leaves = 39,942 leaves, 28 features — NOT a .cbm, no link/panel/window identifier) + W54-A onset rows + D2 per-split occ_ff.
- T3: input field only (conservation-guard adjudicated).
- T4: W54-C own-counts QP refit (no fitted model; candidate md5 `aa8081eabff6c98ae762c5f337760602`).
- D1/D2: per-split priors (20 npz, 0 fallback cells, 16.17M observed cells) + per-split occ_ff (0 fallback links) — the floor's self-calibrating layer. Class split 6 target-identified / 17 seed-invariant / 12 fitted-residue; level discipline PASS (zero train-pooled level carryover).
- Reproduction: prediction-equality (speed ≤1e-14, flow exact, T2/T4 bit-identical); retrain refresh 4/4 bit-identical (6 Nov); RS1R Stage-1 identity |ΔS_state| = 0.000524.

## 2. Code approaches — then vs now

| Dimension | At the start (Sep–Oct) | Now (6 Nov) |
|---|---|---|
| Promotion | Single-month ruler; ship what looks better | **7-gate contract**: deflated 2.67σ bar (~150 trials, luck cannot promote); hidden-box Feb (opened once per experiment); ≥3-month same-sign replication; bundle ablation (marginal <0.002 dropped); LB-vs-CV trust gate; MATH_DESIGN++ pre-registration; red-team LGTM before code; pre-mortems; blameless 72h postmortems |
| Gate | K3 (single-month) | **K3′ (3 Nov, uniform, disclosed post-result)**: Δ_board ≥ +0.010 composite EVERY month AND ΔS_physics ≥ −0.020 AND class cross-month validated. Thresholds carry their unit; panel-level evidence may kill, never promote (M22) |
| Verification | Local ruler scores | Bit-faithful re-serve (max\|Δ\| 1.4e-14–2.8e-14); official vendor evaluator @ `c88cddf5` (weights 0.35/0.30/0.15/0.20 verified in code; empty-road guard confirmed: >20% cells flow <50 vph → S_FD = 0.0); GATE 0 full-month bit-reproduction; prediction-equality acceptance (file md5 is the WRONG test — CatBoost regenerates a 35-byte save-time UUID) |
| Serving statistics | Train-pooled levels (priors, occ_ff) | **Self-calibrating**: D1/D2 re-estimated from each scored split's own released data; zero pooled fallback |
| Selection | March delta | **Class composition, not March delta** (floor certified on composition; selection is Aditya's tap, still pending as of 23:59 IST 6 Nov) |
| Honesty machinery | Ad-hoc | Constitution INSTRUCTIONS.md §3.1 claim labels, §7.5 evidence tiers, §17.1 honest statement; kill record with named mechanisms; disclosures (ws_C glob near-miss, K5 correction, registry column-shift corruption) |

## 3. What the subagent teams went through — 10 lessons I learned from their journeys

**L1. Blind repair (R1–R4, Nov 4): patterns real, every truth-free correction direction wrong.** The blind map's patterns were real (E1–E14, anomaly corr 0.87–0.91) and every correction built from the pattern alone was wrong (R2: "evidence-free" additions are 96% TRUE — inverted; R3: at-T row LAGS, J1's T−5 anchor anticipates; R4a: slope restored, score fell — optimal shrinkage). **Lesson:** a residual pattern is not a mechanism. A correction must be derived from the data-generating process, never from the pattern it corrects. **Improvement:** every future correction lane must name the generating-process mechanism before touching a number — the pattern alone is not a design.

**L2. R1's deeper lesson (Argon Lane 2, Nov 6): the estimator failed, not the phenomenon.** R1 measured group-level corr 0.10 and concluded offsets don't predict error. Per-link corr is 0.83–0.94; the bias is real, static, transferable (Oct↔Jan 0.88). **Lesson:** an aggregate null can hide the very effect being tested — resolution is part of the measurement. **Improvement:** kills must state the resolution they were tested at; a null at one granularity never certifies absence at a finer one. (R1's verdict stands; its mechanism is amended in the kill record — the record is allowed to be wrong.)

**L3. Synthesis sprint ws_D (Nov 6): the obstruction is the conditional mean itself.** 4 target cells touch 4,086 distinct leaves (10.6× Astra's budget); the best surgical leaf is shared by median 112 cells/day; zeroing all firing leaves lands 8.85 km/h short. **Lesson:** when a system sits at a local optimum for its formulation class, sharper edits cannot help — only reformulation or retraining can. **Improvement:** before any edit lane, price the diffuse-vs-localized structure first (leaf-sharing census); if diffuse, kill the edit class without building it.

**L4. ws_C (Nov 6): a real finding can be real and worthless.** E12's pile-up is an exact point mass (39,006 cells at float 120.74999999999999, 31.5× density spike) — and worth +0.00002–0.00007 composite. **Lesson:** reality and value are different verbs. **Improvement:** every confirmed finding gets a served-value price in the same breath as its confirmation.

**L5. Argon Lane 1 / Breakthrough-Max B1 (Nov 6): confirmation ≠ promotion; elegance ≠ arithmetic.** E4 confirmed cleanly (+0.1871 ± 0.0012 IoU/window, 3/3 months, frac>0=1.00) and serves +0.0003–0.0006. B1 is the one genuine MIT-profile candidate (1,644 rescues vs 3 regressions) and dies on magnitude (18× below) and month-decay (Oct→Dec→Jan). Lane (b)'s projection overestimated the masked effect ~4×. **Lesson:** the gate is arithmetic and does not care about profile. Projections are not measurements. **Improvement:** no projected number is ever cited as a measurement; every candidate's gate verdict uses measured per-month composites only.

**L6. Arena-2 (Nov 6): the instrument IS the claim.** A synthetic twin (leaf corr 0.02–0.11 vs real models; baseline 0.751261 vs floor 0.85330; flow bias 1380 per-lane vs real 4198.54 total; 8 synthetic channels vs 95 real features; twin J1 79% zero leaves vs real 0) was treated as a measurement instrument; its outputs were labelled "9/9 PASS K3′", "Tier I FACT", "High Confidence". The +0.05124 spectral optimum is built from hardcoded constants (`0.012θ − 0.016θ²`, `0.55×0.63803×θ`); under their own isotropic model the guard caps the gain at +0.00616. "trend_x_step" does not exist (f22 = `q_ext_up`); 385 "dead-leaf traps" are refuted by parsing real `model_J1.txt` (29 trees split on `step`, zero twice). **Lesson:** if the instrument is synthetic, the numbers are hypotheses, not evidence — no matter how correct the arithmetic inside the simulator is. **Improvement:** any simulator's numbers are labelled HYPOTHESIS until a real-model re-serve exists; the kit's Walsh projector and DAG router are untested transferables, never evidence.

**L7. Arena-2's credit (same review): outside eyes find real seams even when their headlines are wrong.** The W54-D↔ws_B connection (V1 flattered J1 by +0.146) is genuinely new; the Walsh–Hadamard hypothesis and the EB-shrinkage proposal are genuinely new (untested); b11's +0.01491 net is arithmetic our own record never computed (we killed b11 on the −0.004 guard without pricing the composite). **Lesson:** the unbiased rule works — a refutation with numbers is the most valuable outcome, and so is a missed computation. **Improvement:** the award report prices b11's composite explicitly and says why the class/transfer kill still stands.

**L8. Arena-1 (Nov 6): even careful re-derivation drifts.** Their errors were small arithmetic/framing slips — median +0.00336 not +0.0026 (29 increments to 0.95, not 37); 58× is vs the −0.004 guard, not the weight ratio; "send registration today" is wrong (deadline 25 Oct passed — see §4); ladder scope (15 reads, missing the Oct-28 pair and W54-C). Their genuinely new contribution: the ruler noise-floor quantification (±0.005 composite from the two inversions' overshoots 0.00555/0.00582). **Lesson:** every number needs its own verification, including ours — and a quantified failure (the noise floor) is worth more than a narrative about it. **Improvement:** the video states the ±0.005 ruler noise floor as a number, and the third inversion (§4) is named.

**L9. The three ruler-vs-board inversions: the board is the only ruler.** (i) W54-A onset leg: ruler +0.05789 S_queue (≈+0.0174 composite, expected ~0.867) → board +0.00049, overshoot ≈0.0169; (ii) C5: ruler +0.01387 S_queue → board −0.00139, overshoot 0.00555; (iii) W56-L1: ruler +0.01008 → board −0.00280, overshoot 0.00582. **Lesson:** local rulers need their own calibration; the W54-D selector-matched ruler (V1 flattered J1 by +0.146) is the instrument that makes the ruler honest. **Improvement:** ruler calibration is a first-class artifact — the ±0.005 noise floor and the W54-D ruler are named in the video; no local number is quoted without its ruler.

**L10. MIT re-research (lane a, Nov 6): read the primary source, not the blog about the blog.** 10 corrections to Phase 0; the 6× formula is PRIMARY from Astra's own final_report.md L8 (not Kingy-secondary); the edit's benefit is entirely on originally-truncated outputs (+55.3 pp) with 0.0 pp on originally-finished outputs; the Toledo baseline caveat (untouched Qwen 43.95% thinking-off) means the added value under matched settings is unestablished; the harness code was never released. **Lesson:** secondary summaries drift — the primary artifact is the only source. **Improvement:** the video calls the MIT work a **blog post, not a paper**, carries the Toledo caveat, and never claims matched-settings value.

---

## 4. Corrections to our own record (applied in this revision)

1. **Ladder count: 15 → 18 → 21 → 23.** Arena-1 listed 15; lane (a) said 18; my 23:20 count said 21; the true count is **23 scored reads** (the 010F A/B pair, refs 56814979/56815009, was missed by a grep pattern that doesn't match the plural `refs`). The ladder in §1 is the corrected record. The award package and video use 23.
2. **R1 mechanism amended (Argon Lane 2).** R1's verdict stands; its mechanism is wrong at per-link granularity (corr 0.83–0.94 vs 0.10). The kill record carries the amendment (K-ARGON-L2); the award PDF §7 door 4 must carry it too.
3. **Three ruler-vs-board inversions, not two.** The W54-A onset leg is the third (overshoot ≈0.0169, ~3× the ±0.005 noise floor). The PDF's "second ruler-vs-board disagreement" is corrected to three.
4. **"Six doors" is stale framing.** The Nov-4 six (C15, C5, RS1, R1–R4, C4, RS1R) stand, but the final week added: synthesis (no seventh door), Argon E4/E9/E10, Breakthrough-Max (B1/D2 banked-killed, E13 not a defect, E5 class-dead), and the Arena-2 twin refutation. The video says "six doors on Nov 4; every remaining direction tested and closed in the final week, each with a named mechanism."
5. **MIT corrections (lane a, 10 items).** Blog post, not paper; Toledo caveat; harness never released; 6× formula primary; benefit entirely on truncated outputs. The video carries all of them.
6. **Registration: VERIFIED sent and acknowledged (live Gmail check, 6 Nov 23:59 IST).** Aditya sent registration 10 Oct, sent the corrected amendment 14 Oct 11:44 IST (thread `1a1390c0dc5fc9bd`), organizers replied 15 Oct 10:27 IST (`trafficflowbench@gmail.com`, "Re: Traffic Flow Bench Registration") confirming team name PETU LABS. Arena-1's A19 ("send it today") is wrong and must not be repeated. Registration gate: closed, acknowledged.
7. **b11's composite was never priced by us.** Arena-2 noticed it: hard b11 nets +0.01491 composite one-month (0.15×0.63803 + 0.35×(−0.23085)). Our record killed b11 on the −0.004 S_state guard without computing the composite. The kill stands on class/transfer grounds (M8: exact balance fights noisy 5-min data; months independent; ruler suspicion) — but the video prices the +0.01491 explicitly and says why it still dies. (Open sub-question, lane b Y1: is +0.63803 ΔS_physics or ΔS_LWR? If ΔS_LWR, the net would be −0.0170. The primary b11 artifact must be re-read before the video claims the decomposition.)
8. **Registry census counts are method-dependent.** The registry CSV has unquoted-comma column shifts (lane c A21); exact status counts cannot be reproduced from the file. The video/package cite ws_A's adjudicated tally (**62/16/10, status+notes**) and never a raw-status count.
9. **W31 closures are hypothesis [MED], not verdicts.** Downgraded 16 Oct; the video states their status explicitly so no outside team reads them as proofs (Arena-2 did).
10. **The W54-D ruler question is open, not settled.** V1 flattered J1 by +0.146 (0.6791 → 0.5331, selector-matched). The ws_B oracle cap (+0.0042 composite) was priced on the V1 ruler and has never been recomputed on the W54-D ruler. Open item (§7).

## 5. Award PDF corrections (line-level, for the video + package)

- §1/§7: "six final doors closed" → the §4.4 framing above. Add the final-week closures (synthesis, Argon, Breakthrough-Max, Arena-2 refutation) with their mechanisms.
- §7 door 2 (C5): "the second ruler-vs-board disagreement" → **third**; add the ±0.005 ruler noise floor and the W54-A onset leg.
- §7 door 4 (R1–R4): add the R1 mechanism amendment (per-link corr 0.83–0.94; verdict stands).
- §6: "Final selection (6 November) is by class composition" → selection is **pending Aditya's tap** (unconfirmed as of 23:59 IST 6 Nov); competition closes Sat 7 Nov 12:25 IST. Do not present selection as done.
- §7/§9: "#1 ≈ 0.93 at the 3 November snapshot" → **#1 Max Pollard 0.93124 (5 Nov); PETU LABS rank ~393**. Gaps: to #1 +0.07794, to 0.95 +0.09670.
- §7 "What the kill record measures": Kill #71 has five confirmations **plus** the final week's: synthesis (three classes), Argon (E4/E9/E10), Breakthrough-Max (B1/D2) — the honest statement §17.1 now stands with verification behind it, and the video says so.
- MIT framing anywhere in the package/video: **blog post, not paper**; Toledo caveat; harness never released; no matched-settings value claimed.
- §3 Feb protocol: keep, and disclose the ws_C glob near-miss (no violation in outcome) in the same breath as the protocol — it is already in the sprint record.
- Registration: state it as sent 10 Oct + amended 14 Oct + acknowledged 15 Oct (team name PETU LABS confirmed). Never "send it today."

## 6. Improvements applied (the checklist)

- [x] Ladder corrected to 23 reads, with the grep-pattern lesson recorded.
- [x] R1 mechanism amended in kill record + pack (K-ARGON-L2, 02_OUR_CASE.md).
- [x] Third inversion named; ruler noise floor ±0.005 quantified and citable.
- [x] Registration verified live from Gmail (sent + acknowledged).
- [x] MIT corrections (10) absorbed from lane (a); 6× formula primary.
- [x] Evaluator pinned and verified in code (c88cddf5; empty-road guard).
- [x] Registry census: cite ws_A adjudicated tally (62/16/10) only.
- [x] W31 closures labelled hypothesis [MED] in the record.
- [x] Night-stack team dispatched (separate order, 23:20 IST) — stack verified under K3′ before any submission.
- [ ] b11 +0.63803 decomposition (ΔS_physics vs ΔS_LWR) — re-read primary artifact before the video (§7).
- [ ] ws_B oracle cap recomputed on the W54-D selector-matched ruler (§7).
- [ ] Walsh projection tested on a copy of a real .cbm (fix the Y9 main-effect bug first) (§7).
- [ ] Night-stack result (lands overnight; gates the fresh submission).

## 7. The precise final account for the video (exact numbers to say on camera)

- "Our final submission scores **0.85330** on the public month — Kaggle ref **57429904**, 6,980,503 rows, md5 `e6db2a22…`."
- "It is the **certified floor**: our 0.84994 parent plus exactly two changes — split-fidelity fixes D1 and D2 — certified by audit W58-L1 on 20 October."
- "We made **23 board submissions** across the campaign. The floor is the 19th read. **Every candidate read since — four of them — has failed.**"
- "The gap to #1, Max Pollard at **0.93124**, is **+0.07794**. The gap to 0.95 is +0.09670. We do not claim a route to either."
- "Our promotion rule required a candidate to gain **+0.010 on every month** with physics never worse than −0.020. In the final week we tested every remaining direction — the synthesis sprint, the Argon follow-up, a seven-lane breakthrough program, and two outside teams — and **every one closed with a named mechanism**. The largest measured lead, a pooled queue threshold, fails the every-month rule. The one genuine weight-edit candidate decays to zero by January."
- "Three times our own internal ruler promised a gain the board did not give. We measured that: our ruler's noise floor is **±0.005**. The board is the only ruler we trust."
- "The MIT weight-space work that inspired the final program is a **blog post, not a peer-reviewed paper**, and its headline gain was measured with thinking on against a thinking-off baseline — so its added value under matched settings is unestablished. We say that plainly."
- "Registration was sent and acknowledged; the team name is **PETU LABS**. The award package — code and paper — is ready for 10 November."
- "What we claim: the best **honestly evidenced** submission, reproduced bit-identically, with a kill record that measures why it stands. What we do not claim: a route to 0.95, or that the board is wrong about the teams above us."

## 8. Open items before the 12:00 video session

1. **Night-stack result** — the stack's per-month composites and gate verdict (lands overnight; if it clears K3′ and the board read beats the floor, the selection changes — Aditya's tap).
2. **b11 decomposition** — re-read the primary b11 artifact: is +0.63803 ΔS_physics or ΔS_LWR? (If ΔS_LWR, the +0.01491 net is wrong.) One read, decisive for the video.
3. **ws_B oracle cap on the W54-D ruler** — recompute the +0.0042 cap on selector-matched windows (real data, official scorer). If it moves, the ceilings table moves.
4. **Walsh test on a real .cbm copy** — fix the kit's main-effect bug (Y9), apply to a copy, re-serve Oct–Jan. A positive result would be the only new evidence the video could add; a negative one closes the last outside hypothesis.
5. **Selection tap** — Aditya's decision on ref 57429904 (or the night-stack ref, if it clears and beats the floor). Hard cutoff Sat 7 Nov 12:25 IST; video session ~12:00 IST.

---
*Revision written by Petu personally, 6 Nov ~23:57–00:05 IST, from the raw artifacts listed at the top. The night-stack team runs in parallel; this revision does not touch its work. The arena review synthesis (coordinator) is still pending — when it lands, its verdicts fold into §4 as a further correction, not a rewrite.*
