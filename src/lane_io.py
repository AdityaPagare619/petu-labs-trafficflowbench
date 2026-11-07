"""Lane-local IO helpers (work around mleng loader filename assumptions)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

def _resolve_tfb_root():
    """Workspace root for the award package (pure stdlib, import-time safe).

    Precedence: --root CLI arg > TFB_ROOT env var > legacy default.
    Scans sys.argv directly so imported modules see the top-level script's
    --root without argparse having run yet.
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


sys.path.insert(0, str(_resolve_tfb_root() / "builds/dl_blitz/mleng"))
import loaders  # noqa: E402

DATA_ROOT = _resolve_tfb_root() / "data/kaggle_public"
PANELS = ["D7_I10_E", "D7_I10_W", "D7_I210_E", "D7_I210_W", "D7_I405_N",
          "D7_I405_S", "D12_I5_N", "D12_I5_S", "D12_I405_N", "D12_I405_S"]
FAMS = {"D7_I10_E": "D7_I10", "D7_I10_W": "D7_I10", "D7_I210_E": "D7_I210",
        "D7_I210_W": "D7_I210", "D7_I405_N": "D7_I405", "D7_I405_S": "D7_I405",
        "D12_I5_N": "D12_I5", "D12_I5_S": "D12_I5",
        "D12_I405_N": "D12_I405", "D12_I405_S": "D12_I405"}

MASKED_COLS = ["timestamp", "station_id", "link_id", "speed_kmh", "flow_vph",
               "occupancy", "density_occ_linear_vehpkm", "pct_observed",
               "is_score_eligible", "mask_regime", "milepost"]
TRUTH_COLS = ["timestamp", "station_id", "link_id", "speed_kmh", "flow_vph",
              "is_score_eligible", "is_missing", "milepost"]

_FN_DATE = re.compile(r"(\d{4})_(\d{2})_(\d{2})")


def _date_of(path: Path) -> str:
    m = _FN_DATE.search(path.stem)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def iter_masked_days(panel: str, year_month: str):
    """Yield (date_str, regime, masked_day_frame) for a panel-month.

    NOTE: the masked layer is partitioned by mask_regime only (no year_month
    hive partition); filter by parsed filename date."""
    loaders.guard_no_feb(panel, year_month)
    root = DATA_ROOT / "corridors" / panel / "train" / "mainline_states_masked"
    for rdir in sorted(root.glob("mask_regime=*")):
        regime = rdir.name.split("=")[1]
        for path in sorted(rdir.glob("*.parquet")):
            date = _date_of(path)
            if not date.startswith(year_month):
                continue
            df = pd.read_parquet(path, columns=[c for c in MASKED_COLS])
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df["link_id"] = df["link_id"].astype(str)
            yield date, regime, df


def iter_truth_days(panel: str, year_month: str):
    """Yield (date_str, unmasked_truth_frame) for a panel-month."""
    loaders.guard_no_feb(panel, year_month)
    root = DATA_ROOT / "corridors" / panel / "train" / "mainline_states" / f"year_month={year_month}"
    for path in sorted(root.glob("*.parquet")):
        df = pd.read_parquet(path, columns=[c for c in TRUTH_COLS])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["link_id"] = df["link_id"].astype(str)
        yield _date_of(path), df


def load_ramps_day(panel: str, date_str: str) -> pd.DataFrame:
    ym = date_str[:7]
    r = loaders.load_ramps(panel, [ym])
    if len(r) == 0:
        return r
    return r[r["timestamp"].dt.normalize() == pd.Timestamp(date_str)].copy()
