"""Proof that the W28 candidate differs from production ONLY in T1 state
speed/flow values: identical row count/ids/tasks, queue_pred and path_flow
bit-identical everywhere, state rows keyed identically.

Additionally compares the candidate's state rows to the W27 bundle file
(the 0.81458 leader) to show the T1 swap moves in the intended direction.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _resolve_tfb_root():
    """Workspace root for the award package (pure stdlib, import-time safe).

    Precedence: --root CLI arg > TFB_ROOT env var > legacy default.
    """
    import os
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


TFB = str(_resolve_tfb_root())
PROD = f"{TFB}/submissions/submission_exp006gk_v1.csv"
CAND = f"{TFB}/submissions/submission_w28_scale_v1.csv"
W27 = f"{TFB}/submissions/submission_w27_candidate_v1.csv"

p = pd.read_csv(PROD)
c = pd.read_csv(CAND)
print(f"prod rows {len(p):,}  cand rows {len(c):,}")
assert len(p) == len(c) == 6980503
assert (p["submission_id"].to_numpy() == c["submission_id"].to_numpy()).all()
assert (p["task"].to_numpy() == c["task"].to_numpy()).all()
print("row count / ids / task column: IDENTICAL")

for col in ("queue_pred", "path_flow"):
    same = (p[col].to_numpy() == c[col].to_numpy()).all()
    print(f"{col}: bit-identical everywhere = {same}")
    assert same

st = (p["task"] == "state").to_numpy()
nonstate = ~st
for col in ("speed_kmh", "flow_vph"):
    assert (p.loc[nonstate, col].to_numpy() == 0).all()
    assert (c.loc[nonstate, col].to_numpy() == 0).all()

ds = (p.loc[st, "speed_kmh"].to_numpy() != c.loc[st, "speed_kmh"].to_numpy())
df = (p.loc[st, "flow_vph"].to_numpy() != c.loc[st, "flow_vph"].to_numpy())
n_st = int(st.sum())
print(f"state rows: {n_st:,}; speed changed {int(ds.sum()):,} ({ds.mean():.3%}); "
      f"flow changed {int(df.sum()):,} ({df.mean():.3%})")
print(f"state speed: cand mean {c.loc[st,'speed_kmh'].mean():.3f} vs prod "
      f"{p.loc[st,'speed_kmh'].mean():.3f}; max {c.loc[st,'speed_kmh'].max():.1f}")
print(f"state flow : cand mean {c.loc[st,'flow_vph'].mean():.3f} vs prod "
      f"{p.loc[st,'flow_vph'].mean():.3f}; max {c.loc[st,'flow_vph'].max():.1f}")
assert np.isfinite(c.loc[st, ["speed_kmh", "flow_vph"]].to_numpy()).all()
assert (c.loc[st, "speed_kmh"] >= 0).all() and (c.loc[st, "flow_vph"] >= 0).all()
assert (c.loc[st, "queue_pred"] == 0).all() and (c.loc[st, "path_flow"] == 0).all()
q = (p["task"] == "queue").to_numpy()
assert set(np.unique(c.loc[q, "queue_pred"])).issubset({0.0, 1.0})
print("sanity: finite, nonneg, irrelevant columns zeroed, queue binary — PASS")

w = pd.read_csv(W27, usecols=["speed_kmh", "flow_vph"])
ps = p.loc[st, "speed_kmh"].to_numpy()
cs = c.loc[st, "speed_kmh"].to_numpy()
ws = w.loc[st, "speed_kmh"].to_numpy()
pf_ = p.loc[st, "flow_vph"].to_numpy()
cf_ = c.loc[st, "flow_vph"].to_numpy()
wf_ = w.loc[st, "flow_vph"].to_numpy()
print(f"mean|d_s|: scale-vs-prod {np.abs(cs-ps).mean():.4f}, "
      f"scale-vs-w27 {np.abs(cs-ws).mean():.4f}, w27-vs-prod {np.abs(ws-ps).mean():.4f}")
print(f"mean|d_f|: scale-vs-prod {np.abs(cf_-pf_).mean():.4f}, "
      f"scale-vs-w27 {np.abs(cf_-wf_).mean():.4f}, w27-vs-prod {np.abs(wf_-pf_).mean():.4f}")
print("DIFF PROOF COMPLETE: candidate == production outside T1 state values")
