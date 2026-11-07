# Competition rules

Source: 2026 IEEE Big Data Cup — TrafficFlowBench (`2026-ieee-big-data-traffic-flow-bench`, Kaggle). Repo: `github.com/jacky850/trafficflowbench-public` (evaluator pinned at commit `c88cddf5`).

## Task

Predict the full traffic state of a motorway network from masked sensor observations:

| Leg | Task | Output |
|---|---|---|
| T1 | State | Per-link 5-minute speed and flow |
| T2 | Queue | Queue onset flags (J1 ongoing + onset rows) |
| T3 | Physics | Physics consistency of the predicted field (FD + LWR) |
| T4 | ODME | Origin–destination matrix estimation |

## Scoring

```
S_total = 0.35·S_state + 0.30·S_queue + 0.15·S_physics + 0.20·S_ODME
S_state = 0.54·S_speed + 0.46·S_flow
S_physics = (S_FD + 2·S_LWR) / 3
```

- The public leaderboard scores **one validation month** (March 2031).
- Final standings use a **different, independently generated hidden month** (April 2031).
- Eligibility: ≥75% observed data per submission.
- Task 2 excludes D12_I405_N/S from its IoU; Task 3 derives FD/LWR from Task 1 values; Mode A ramp coverage 0.756.
- S_ODME = 0.45·S_od + 0.25·S_link + 0.15·S_dev + 0.15·S_attr.
- Empty-road guard (verified in the evaluator code): if >20% of submitted target cells in a panel×regime have flow < 50 vph, S_FD = 0.0.

## Required leg gains (for +0.010 composite, single leg)

| Leg | Δ needed [task] |
|---|---|
| T1 S_state | +0.0286 |
| T2 S_queue | +0.0333 |
| T3 S_physics | +0.0667 |
| T4 S_ODME | +0.0500 |

## Award

- Registration by **Oct 25, 2026** (ours: sent 10 Oct, amended 14 Oct, acknowledged 15 Oct — team name **PETU LABS**).
- Code + paper by **Nov 10, 2026, 23:59 AoE**.
- Top-10 private-pool teams enter the review pool. Reproducibility: organizers rerun team code; predictions must match the private-leaderboard score within **1%**.
- Final Score = **0.85·L + 0.15·R**, where L is the private-leaderboard score (min-max normalized in the pool) and R is the review score: **40 technical soundness + 40 analysis/insight + 20 clarity**.
- Prizes: Gold $1,500 / Silver $1,000 / Bronze $500. Winners present at IEEE BigData 2026, Dec 14–17, Phoenix.
- A K-12 Student Award contemplates minors; the competition's Foundational Rules require 18+ or age of majority (18 in India either way). Our lead is 24.
