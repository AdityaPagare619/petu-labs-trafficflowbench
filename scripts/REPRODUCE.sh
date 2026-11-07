#!/bin/bash
# REPRODUCE.sh — one-command award-package reproduction (one-panel acceptance)
#
# PETU LABS · TrafficFlowBench · W39-A (2026-10-15)
# Candidate: 0.85330 floor (ref 57429904) — this script reproduces the
# floor's T1 leg (W28 one-panel inference, D7_I10_W). The drill was first
# run on the 0.81787 candidate (ref 57065852, superseded 2026-11-05);
# the T1 leg and its expected md5s are unchanged.
#
# What this does:
#   1. Verifies the Python environment (3.12 + pinned requirements).
#   2. Runs the model-md5 gate (4 shipped .cbm files vs STATUS.json).
#   3. Re-runs the T1 inference for ONE panel (D7_I10_W, both splits) from
#      scratch and asserts the two expected md5s (the proven acceptance test
#      from HARDENING_REPORT.md §1).
#
# What this does NOT do (see REHEARSAL_RUNBOOK.md for the full path):
#   - the full 10-panel inference+merge rehearsal (Stages A/C/D)
#   - the 4-model from-scratch retrain (Stage B; acceptance = prediction-
#     equality via verify_retrain.py, NOT file-md5 — see
#     FROZEN_ARTIFACT_DISCLOSURE.md §4)
#
# Usage: ./REPRODUCE.sh [--root /path/to/tfb]
#   --root overrides the workspace root (default /home/hatch/workspace/tfb);
#   TFB_ROOT env var also honored. The script never writes outside the
#   workspace root except for a small backup dir it creates and restores.
#
# Iron rules: no Kaggle submissions, Feb-2031 never touched, shipped files
# are read-only (the script only READS them; it writes fresh outputs).

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

AWARD="$ROOT/ops/award_pkg"
GATES="$ROOT/builds/w28_scale_bundle_gates"
OUTDIR="$GATES/cand_states"
PANEL="D7_I10_W"

# Expected md5s (HARDENING_REPORT.md §1 — verified 2026-10-12)
EXP_VAL="8798526e79348bee5d326372a58a7c7a"
EXP_PRIV="705d4ffbeff95f39a108558bd7f72720"

echo "=== REPRODUCE.sh ==="
echo "workspace root: $ROOT"

# 1. Python environment
if [ -x "$ROOT/venv/bin/python" ]; then
  PY="$ROOT/venv/bin/python"
else
  PY="python3"
fi
echo "--- [1/4] environment: $($PY --version 2>&1)"
"$PY" -c "
import sys
assert sys.version_info[:2] == (3, 12), 'need Python 3.12'
missing = []
for pkg in ('catboost','lightgbm','pandas','numpy','pyarrow','scipy','osqp','joblib'):
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    print('MISSING packages:', missing)
    print('Install with: pip install -r $AWARD/requirements.txt')
    sys.exit(1)
import catboost, lightgbm, pandas, numpy, pyarrow, scipy, osqp, joblib
pins = {'catboost':'1.2.10','lightgbm':'4.7.0','pandas':'3.0.6','numpy':'2.5.3',
        'pyarrow':'25.0.1','scipy':'1.18.1','osqp':'1.1.3','joblib':'1.6.0'}
got = {'catboost':catboost.__version__,'lightgbm':lightgbm.__version__,
       'pandas':pandas.__version__,'numpy':numpy.__version__,
       'pyarrow':pyarrow.__version__,'scipy':scipy.__version__,
       'osqp':osqp.__version__,'joblib':joblib.__version__}
bad = {k:(got[k],pins[k]) for k in pins if got[k]!=pins[k]}
if bad:
    print('VERSION MISMATCH (want pinned):', bad); sys.exit(1)
print('environment OK: Python 3.12, all 8 pins match')
"

# 2. Model-md5 gate (shipped .cbm files vs the frozen MODEL_MD5 table)
#    Uses infer_w28.verify_models() directly — single source of truth.
echo "--- [2/4] model-md5 gate"
"$PY" - "$GATES" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import infer_w28
infer_w28.verify_models()
EOF

# 3. One-panel inference repro (fresh: move existing outputs aside first)
echo "--- [3/4] one-panel inference repro ($PANEL, both splits)"
BACKUP="$AWARD/reproduce_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP"
for split in validation private; do
  f="$OUTDIR/cand_state_${split}_${PANEL}.csv"
  if [ -f "$f" ]; then
    mv "$f" "$BACKUP/"
    echo "  backed up existing $f"
  fi
done
"$PY" "$GATES/infer_w28.py" --mode valpriv --only-panel "$PANEL" --root "$ROOT"

# 4. Assert the two expected md5s
echo "--- [4/4] md5 assertions"
pass=true
for split in validation private; do
  f="$OUTDIR/cand_state_${split}_${PANEL}.csv"
  [ -f "$f" ] || { echo "  MISSING output: $f"; pass=false; continue; }
  got=$(md5sum "$f" | cut -d' ' -f1)
  if [ "$split" = "validation" ]; then exp="$EXP_VAL"; else exp="$EXP_PRIV"; fi
  if [ "$got" = "$exp" ]; then
    echo "  $split: $got MATCH"
  else
    echo "  $split: $got vs expected $exp MISMATCH"
    pass=false
  fi
done

if $pass; then
  echo "=== REPRODUCE.sh: PASS ==="
else
  echo "=== REPRODUCE.sh: FAIL ==="
  exit 1
fi
