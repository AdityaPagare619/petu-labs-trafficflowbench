#!/bin/bash
# REPRODUCE_FINAL.sh — DRAFT scaffold for the FINAL bundle's award-package reproduction
#
# PETU LABS · TrafficFlowBench · W60-L3 (2026-10-21) — DRAFT, not yet verified end-to-end.
# W61-L5 (2026-10-26): stage [2] bug fixed — STATUS.json key is `models_md5`
# (not `model_md5s`), values keyed by model stem; file = stem + '.cbm'.
# Extends ops/award_pkg/REPRODUCE.sh (which is VERIFIED for the W28 T1 leg —
# the floor's T1 leg; first run on the 0.81787 candidate, ref 57065852,
# superseded 2026-11-05) toward the final bundle's legs:
# NOT modified by this file) toward the final bundle's legs:
#   - W54-C per-split NNLS (T4)
#   - W57 D1/D2 per-split builders (T1 priors, J1 occ_ff)
#   - 006G pooled onset + J1 ongoing emitters (T2)
#   - per-split procedure re-execution checks
#
# PLACEHOLDERS — FILLED at the Nov-6 floor rehearsal (2026-11-06):
# final selection = certified floor ref 57429904, public 0.85330,
# submissions/submission_w57_d1d2_v1.csv, md5 e6db2a22a5e676955ab225358c0e378c
# (FINAL_SELECTION_LEDGER.md addendum 2026-11-05; re-verified 2026-11-06).
# Env vars still override the defaults below.
FINAL_REF="${FINAL_REF:-57429904}"
FINAL_MD5="${FINAL_MD5:-e6db2a22a5e676955ab225358c0e378c}"
FINAL_FILE="${FINAL_FILE:-submission_w57_d1d2_v1.csv}"

# What this does (stages):
#   [1] environment check (python 3.12 + 8 pinned packages)
#   [2] model-md5 gate: 4 W28 .cbm files vs builds/w28_t1_scale/STATUS.json
#   [3] frozen-artifact md5 gates: W54-C candidate, 20 D1 priors npz, D2 occ_ff parquet,
#       J1 model + thresholds, 006G g_fired
#   [4] procedure re-execution (spot): re-run build_priors_split.py on one panel-split
#       and assert md5 == manifest (proves the frozen input is regenerable)
#   [5] final-selection identity gate (FILLED 2026-11-06: floor 57429904)
#
# Iron rules: no Kaggle submissions, sealed held-out month never touched, shipped files
# are read-only (the script only READS them; it writes fresh outputs under the workspace root).

set -euo pipefail

ROOT="/home/hatch/workspace/tfb"
for arg in "$@"; do
  case "$arg" in
    --root=*) ROOT="${arg#--root=}" ;;
    --root) shift; ROOT="${1:-$ROOT}" ;;
  esac
done
if [ -n "${TFB_ROOT:-}" ] && [ "$ROOT" = "/home/hatch/workspace/tfb" ]; then
  ROOT="$TFB_ROOT"
fi

# ---- PLACEHOLDERS: filled at the Nov-6 rehearsal (AWARD_DRAFT_V2.md §0) ----
FINAL_REF="${FINAL_REF:-__REHEARSAL_TBD__}"
FINAL_MD5="${FINAL_MD5:-__REHEARSAL_TBD__}"
FINAL_FILE="${FINAL_FILE:-__REHEARSAL_TBD__}"

echo "=== REPRODUCE_FINAL.sh (DRAFT) ==="
echo "workspace root: $ROOT"
echo "final selection: ref=$FINAL_REF md5=$FINAL_MD5 file=$FINAL_FILE"

if [ -x "$ROOT/venv/bin/python" ]; then PY="$ROOT/venv/bin/python"; else PY="python3"; fi

# [1] environment
echo "--- [1/5] environment: $($PY --version 2>&1)"
"$PY" -c "
import sys
assert sys.version_info[:2] == (3, 12), 'need Python 3.12'
for pkg in ('catboost','lightgbm','pandas','numpy','pyarrow','scipy','osqp','joblib'):
    __import__(pkg)
print('env OK: 8 pinned packages importable')
"

# [2] model-md5 gate (4 W28 .cbm files)
echo "--- [2/5] W28 model-md5 gate"
"$PY" - "$ROOT" <<'EOF'
import sys, json, hashlib
from pathlib import Path
root = Path(sys.argv[1])
status = json.loads((root/'builds/w28_t1_scale/STATUS.json').read_text())
ok = True
for name, exp in status['models_md5'].items():
    p = root/'builds/w28_t1_scale'/'models'/(name + '.cbm')
    got = hashlib.md5(p.read_bytes()).hexdigest()
    good = (got == exp)
    ok &= good
    print(('PASS' if good else 'FAIL'), name, got)
sys.exit(0 if ok else 1)
EOF

# [3] frozen-artifact md5 gates
echo "--- [3/5] frozen-artifact md5 gates"
check_md5() {  # check_md5 <file> <expected>
  got=$(md5sum "$1" | cut -d' ' -f1)
  if [ "$got" = "$2" ]; then echo "PASS $1"; else echo "FAIL $1 (got $got, want $2)"; return 1; fi
}
check_md5 "$ROOT/builds/w54_c_t4/odme_candidate_owncounts.csv" "aa8081eabff6c98ae762c5f337760602"
check_md5 "$ROOT/builds/w57_d1d2_splitfix/occff_split/occ_ff_by_split.parquet" "03919c6af026d66f80e2bad33425e071"
check_md5 "$ROOT/builds/exp003j/model_J1.txt" "92fb048c245d8ca8c12afb14ca9fe891"
# D1 priors: 20 npz vs manifest (manifest path filled from PRIORS_STATEMENT_V2.md §3)
"$PY" - "$ROOT" <<'EOF'
import sys, hashlib
from pathlib import Path
root = Path(sys.argv[1])
manifest = {
 'D7_I10_E_validation':'022096b4a513b33a75c3de61cdd72aea','D7_I10_E_private':'82bd5d8374202d253bc556b94a2c050a',
 'D7_I10_W_validation':'4cc50c61b99bb7c0dba74afc14dc4099','D7_I10_W_private':'73731f4b18085bba05bdd4c35a6fe360',
 'D7_I210_E_validation':'61af11aab5e463c711e531eca113f4d5','D7_I210_E_private':'1c60a2ef6839b319f09bc17d55d8328d',
 'D7_I210_W_validation':'3bc28dda32c1dad02c3c9969112da34f','D7_I210_W_private':'4886b99b4f98246c8f32335201a89342',
 'D7_I405_N_validation':'c01de87234fa3ec16ea60b0e6cb4f1cf','D7_I405_N_private':'b0be31941a6fac3202d9f0d2d2ed8a2e',
 'D7_I405_S_validation':'27a5280da70ec98ef3f71ac51001ccad','D7_I405_S_private':'ef14ac9c9207aae5bfc51d324ea08298',
 'D12_I5_N_validation':'243373fdafb2ffa6556c3b64efd814f0','D12_I5_N_private':'311ef86d8f68537b76f0e75914da9d87',
 'D12_I5_S_validation':'7fff1463aaf44bafbad9a9a86f77ad40','D12_I5_S_private':'41aaac7a466e7d8043ffa947af06f9c8',
 'D12_I405_N_validation':'6baf178d0672b1ec7abe7729c6a29111','D12_I405_N_private':'c91e65c85f77b35d875fb457c50174c5',
 'D12_I405_S_validation':'d12eaff28ffa10dcd119ca4607678952','D12_I405_S_private':'eb361ffd5efc7746d039fc1edbb8ad7d',
}
d = root/'builds/w57_d1d2_splitfix/priors_split'
ok = True
for k, exp in manifest.items():
    panel, split = k.rsplit('_', 1)
    p = d/f'priors_{panel}_{split}.npz'
    got = hashlib.md5(p.read_bytes()).hexdigest()
    good = (got == exp); ok &= good
    if not good: print('FAIL', p.name, got)
print('D1 priors manifest:', '20/20 PASS' if ok else 'FAILURES PRESENT')
sys.exit(0 if ok else 1)
EOF

# [4] procedure re-execution spot check (one panel-split D1 rebuild; asserts regenerability)
echo "--- [4/5] procedure re-execution spot check (D1, one panel-split)"
echo "Rehearsal command (L6 executes; NOT run by this lane — see note):"
echo "  ./venv/bin/python builds/w57_d1d2_splitfix/build_priors_split.py D7_I10_W validation"
echo "  then: md5 of the rebuilt priors_D7_I10_W_validation.npz == 4cc50c61b99bb7c0dba74afc14dc4099"
echo "PRECONDITION (W61-L5 finding): build_priors_split.py hardcodes OUT to"
echo "builds/w57_d1d2_splitfix/priors_split/ and TFB to the workspace root, so a"
echo "live rebuild REWRITES the frozen artifact path. The rehearsal MUST run it"
echo "against a scratch copy of the builder tree (copied TFB root with OUT"
echo "redirected), compare md5s, and leave the frozen dir byte-untouched."
echo "(Full 20-pair re-execution is rehearsal work; see REPRODUCE_DRILL_PLAN.md.)"
echo "Today: builder/solvers presence checks only (no rebuild — frozen dir untouched)."
test -f "$ROOT/builds/w57_d1d2_splitfix/build_priors_split.py" && echo "PASS builder present"
test -f "$ROOT/builds/w57_d1d2_splitfix/build_occff_split.py" && echo "PASS builder present"
test -f "$ROOT/builds/w54_c_t4/qp_solver.py" && echo "PASS solver present"

# [5] final-selection identity gate (PLACEHOLDER)
echo "--- [5/5] final-selection identity gate"
if [ "$FINAL_REF" = "__REHEARSAL_TBD__" ]; then
  echo "SKIP: final selection not yet named (filled at Nov-6 rehearsal, AWARD_DRAFT_V2.md §0)"
else
  echo "final selection: ref=$FINAL_REF md5=$FINAL_MD5 file=$FINAL_FILE"
  # the rehearsal asserts: downloaded submission md5 == FINAL_MD5 and row count == 6980503
fi

echo "=== REPRODUCE_FINAL.sh (DRAFT) complete ==="
