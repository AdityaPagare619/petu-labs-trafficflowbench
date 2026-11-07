"""Shared data loaders for the TrafficFlowBench Deep Learning Blitz.

One home for every data access pattern the four model lanes (UNet, CNN, Tree,
MLP) need: efficient month-partitioned parquet reads of mainline + ramp
states, network topology, task templates, and the OD operator.

IRON RULES
----------
1. **Feb-2031 (``2031-02``) is never touched.** Every public entry point calls
   :func:`guard_no_feb`; any path, month string, or filter that mentions
   ``2031-02`` raises ``ValueError`` before any I/O happens.
2. **Deterministic.** :func:`seed_all` seeds Python, NumPy and (if present)
   PyTorch so lane training and shuffles reproduce bit-for-bit.
3. **Memory-efficient.** Reads select only the requested columns and stream
   through ``pyarrow``; lanes that train over many months should use
   :func:`iter_days` instead of loading everything at once.

Month conventions
-----------------
The released train split spans ``2030-06`` .. ``2031-02``. The campaign's
pseudo-month CV labels map to the calendar months:

    Jan -> 2031-01,  Oct -> 2030-10,  Nov -> 2030-11,  Dec -> 2030-12

``PSEUDO_MONTHS`` carries that mapping; ``CV_TRAIN_MONTHS`` is every train
month except Feb-2031 (``2031-02`` is excluded here, not merely by policy).

007D-style universe option
-------------------------
``build_universe`` assembles a spacetime (cell, dt) "universe" over a states
frame following the EXP-007D discretization conventions:

- a *cell* is (timestamp, link_id);
- a cell is *observable* when every scored channel is present, i.e.
  ``is_score_eligible``;
- a *transition* (cell_t -> cell_t+1 on the same link) is observable only when
  both endpoints are observable and ``dt <= 5.1/60 hours`` (the 5-minute
  release step plus tolerance).

This is exposed as an *option* (``universe="observable"``) for lanes that do
physics/LWR-style training on the mainline states.

Vendor scoring constants live here too, copied verbatim from
``competition_contract.json`` (single source of truth for the lanes).
"""

from __future__ import annotations

import os
import random
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

def _resolve_tfb_root():
    """Workspace root for the award package (pure stdlib, import-time safe).

    Precedence: --root CLI arg > TFB_ROOT env var > legacy default.
    Scans sys.argv directly so imported modules see the top-level script's
    --root without argparse having run yet.
    """
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


DATA_ROOT = _resolve_tfb_root() / "data/kaggle_public"
VENDOR_SRC = _resolve_tfb_root() / "vendor/trafficflowbench-public/src"

# Make the vendor task packages importable for reuse (scoring constants etc.).
if str(VENDOR_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_SRC))

# --------------------------------------------------------------------------
# Identity / calendar constants
# --------------------------------------------------------------------------

PANELS = [
    "D7_I10_E", "D7_I10_W", "D7_I210_E", "D7_I210_W",
    "D7_I405_N", "D7_I405_S", "D12_I5_N", "D12_I5_S",
    "D12_I405_N", "D12_I405_S",
]
PANEL_TO_FAMILY = {p: "_".join(p.split("_")[:2]) for p in PANELS}

#: Campaign pseudo-month labels -> calendar year_month. "Jan/Oct/Nov/Dec" are
#: the four held-out pseudo-months used for CV; Feb-2031 (2031-02) is the
#: hidden box and never appears here.
PSEUDO_MONTHS = {"Jan": "2031-01", "Oct": "2030-10", "Nov": "2030-11", "Dec": "2030-12"}

#: Every train month the CV pool may use. Feb-2031 is excluded by construction.
CV_TRAIN_MONTHS = [
    "2030-06", "2030-07", "2030-08", "2030-09",
    "2030-10", "2030-11", "2030-12", "2031-01",
]

#: The hidden month. Hard-blocked everywhere by :func:`guard_no_feb`.
FORBIDDEN_MONTH = "2031-02"

REGIMES = ("R1", "R2", "R3")
REGIME_BLANK_SHARE = {"R1": 0.20, "R2": 0.30, "R3": 0.50}

# Task 1 scoring constants, verbatim from config/competition_contract.json.
SPEED_WEIGHT = 0.54
FLOW_WEIGHT = 0.46
SPEED_NORMALIZER = 25.0
FLOW_NORMALIZER = 600.0  # per-lane vph

# Overall score weights (release.score_overall.WEIGHTS).
OVERALL_WEIGHTS = {"state": 0.35, "queue": 0.30, "physics": 0.15, "odme": 0.20}

# Task 4 decomposition weights (competition_contract.json, "odme").
ODME_WEIGHTS = {"od": 0.45, "link": 0.25, "dev": 0.15, "attr": 0.15}

# 007D-style universe transition cap: 5.1/60 hours = 5.1 minutes.
UNIVERSE_DT_MAX_HOURS = 5.1 / 60.0


# --------------------------------------------------------------------------
# IRON RULE: Feb-2031 guard
# --------------------------------------------------------------------------

def guard_no_feb(*values: object) -> None:
    """Raise ``ValueError`` if anything references Feb-2031 (``2031-02``).

    Checks every positional argument (strings, Paths, lists/tuples/dicts of
    them) for the forbidden month token. Call this before any file-system
    access so that even a directory *listing* of Feb-2031 cannot happen.
    """
    def _check(v: object) -> None:
        if v is None:
            return
        if isinstance(v, (str, Path, os.PathLike)):
            s = str(v)
            if FORBIDDEN_MONTH in s or "203102" in s or "2031_02" in s:
                raise ValueError(
                    f"FORBIDDEN: reference to hidden month Feb-2031 detected in {s!r}. "
                    "The hidden box is never touched."
                )
        elif isinstance(v, dict):
            for k, vv in v.items():
                _check(k); _check(vv)
        elif isinstance(v, (list, tuple, set, frozenset)):
            for vv in v:
                _check(vv)

    for v in values:
        _check(v)


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def seed_all(seed: int = 20261005) -> int:
    """Seed Python, NumPy, and PyTorch (if installed) for reproducibility.

    Returns the seed so lanes can log it. Also sets ``PYTHONHASHSEED``
    process-wide for the current process (child processes inherit it).
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed % (2 ** 32))
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass
    return seed


# --------------------------------------------------------------------------
# Month / panel helpers
# --------------------------------------------------------------------------

def pseudo_to_year_month(label: str) -> str:
    """Map a CV pseudo-month label ('Jan', 'Oct', 'Nov', 'Dec') to year_month."""
    guard_no_feb(label)
    try:
        return PSEUDO_MONTHS[label]
    except KeyError:
        raise ValueError(f"unknown pseudo-month {label!r}; expected one of {sorted(PSEUDO_MONTHS)}")


def train_months_for_fold(heldout_labels: Iterable[str]) -> list[str]:
    """Train months for a fold = all CV train months minus the held-out ones."""
    heldout = {pseudo_to_year_month(l) for l in heldout_labels}
    months = [m for m in CV_TRAIN_MONTHS if m not in heldout]
    guard_no_feb(months)
    return months


def month_path(panel: str, year_month: str, kind: str = "mainline_states",
               masked: bool = False) -> Path:
    """Hive-partitioned directory for one panel-month of state data."""
    guard_no_feb(panel, year_month, kind)
    layer = "mainline_states_masked" if masked else kind
    return DATA_ROOT / "corridors" / panel / "train" / layer / f"year_month={year_month}"


# --------------------------------------------------------------------------
# Mainline + ramp state loading
# --------------------------------------------------------------------------

_MAINLINE_COLUMNS = [
    "date", "timestamp", "station_id", "link_id", "speed_kmh", "flow_vph",
    "occupancy", "density_occ_linear_vehpkm", "pct_observed",
    "is_observed", "is_imputed", "is_score_eligible", "is_missing",
]

_MASKED_COLUMNS = [
    "timestamp", "station_id", "link_id", "speed_kmh", "flow_vph",
    "occupancy", "density_occ_linear_vehpkm", "pct_observed",
    "is_score_eligible", "mask_regime",
]


def load_mainline(panel: str, months: Iterable[str],
                  masked: bool = False, regime: Optional[str] = None,
                  columns: Optional[list[str]] = None,
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None) -> pd.DataFrame:
    """Load mainline states for a panel across months (unmasked or masked).

    Parameters
    ----------
    panel: corridor panel id, e.g. ``"D7_I10_E"``.
    months: year_month strings, e.g. ``["2030-10", "2030-11"]``.
    masked: if True, read the Task-1 masked layer (targets blanked).
    regime: when masked, restrict to one ``mask_regime`` partition
        (``"R1"/"R2"/"R3"``); the masked layer is partitioned by regime.
    columns: subset of columns to read (memory control). Defaults to a
        useful working set.
    date_from, date_to: inclusive ``"YYYY-MM-DD"`` bounds pushed into the
        parquet scan.

    Returns a DataFrame with ``timestamp`` parsed to UTC datetimes. Never
    touches Feb-2031 (guarded).
    """
    months = list(months)
    guard_no_feb(panel, months, date_from, date_to)
    if panel not in PANELS:
        raise ValueError(f"unknown panel {panel!r}")
    if masked and regime is not None and regime not in REGIMES:
        raise ValueError(f"unknown regime {regime!r}")

    default_cols = _MASKED_COLUMNS if masked else _MAINLINE_COLUMNS
    cols = list(columns) if columns else default_cols

    frames = []
    for m in months:
        if masked:
            # The masked layer is partitioned by regime, not by month: each
            # regime directory holds all months' files (named by date).
            root = (DATA_ROOT / "corridors" / panel / "train"
                    / "mainline_states_masked")
            if regime is not None:
                root = root / f"mask_regime={regime}"
            if not root.exists():
                continue
            wanted = [p for p in sorted(root.glob("*.parquet"))
                      if (_date_from_filename(p) or "")[:7] == m]
            if not wanted:
                continue
            dataset = ds.dataset(wanted, format="parquet")
        else:
            root = month_path(panel, m, masked=False)
            if not root.exists():
                continue
            dataset = ds.dataset(str(root), format="parquet", partitioning="hive")
        filt = None
        if date_from is not None or date_to is not None:
            import pyarrow.compute as pc
            conds = []
            if date_from is not None:
                conds.append(pc.field("date") >= date_from)
            if date_to is not None:
                conds.append(pc.field("date") <= date_to)
            filt = conds[0] if len(conds) == 1 else (conds[0] & conds[1])
        # "date" must be materialized whenever a date filter is applied.
        read_cols = list(cols)
        if filt is not None and "date" not in read_cols:
            read_cols = read_cols + ["date"]
        table = dataset.to_table(columns=read_cols, filter=filt)
        df = table.to_pandas()
        if "date" not in cols and "date" in df.columns:
            df = df.drop(columns=["date"])
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    if "station_id" in out.columns:
        out["station_id"] = out["station_id"].astype(str)
    if "link_id" in out.columns:
        out["link_id"] = out["link_id"].astype(str)
    return out


def iter_days(panel: str, months: Iterable[str], masked: bool = False,
              regime: Optional[str] = None,
              columns: Optional[list[str]] = None,
              dates: Optional[Iterable[str]] = None) -> Iterator[pd.DataFrame]:
    """Yield one calendar day of mainline states at a time (low-RAM lanes).

    Parameters mirror :func:`load_mainline`; ``dates`` optionally restricts to
    a set of ``"YYYY-MM-DD"`` strings. This is the recommended pattern for
    training loops that cannot hold a full month (~40-60M rows/panel) in RAM.
    """
    months = list(months)
    guard_no_feb(panel, months, dates)
    date_list = sorted(set(dates)) if dates is not None else None
    seen: set[str] = set()
    for m in months:
        if masked:
            root = (DATA_ROOT / "corridors" / panel / "train"
                    / "mainline_states_masked")
            if regime is not None:
                root = root / f"mask_regime={regime}"
            if not root.exists():
                continue
            files = [p for p in sorted(root.glob("*.parquet"))
                     if (_date_from_filename(p) or "")[:7] == m]
        else:
            root = month_path(panel, m, masked=False)
            if not root.exists():
                continue
            files = sorted(root.glob("*.parquet"))
        for path in files:
            day = _date_from_filename(path)
            if day is None:
                continue
            guard_no_feb(day)
            if date_list is not None and day not in set(date_list):
                continue
            if day in seen:
                continue
            seen.add(day)
            cols = list(columns) if columns else (_MASKED_COLUMNS if masked else _MAINLINE_COLUMNS)
            df = pd.read_parquet(path, columns=[c for c in cols if c in pq.ParquetFile(path).schema_arrow.names])
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            if "station_id" in df.columns:
                df["station_id"] = df["station_id"].astype(str)
            if "link_id" in df.columns:
                df["link_id"] = df["link_id"].astype(str)
            df["date"] = day
            yield df


def truth_at_targets(panel: str, months: Iterable[str],
                    use_cache: bool = True) -> pd.DataFrame:
    """Unmasked truth restricted to the panel's T1 template target keys.

    Returns one row per (timestamp, station_id, link_id, mask_regime) target
    in the requested months, with the unmasked ``speed_kmh``/``flow_vph``,
    restricted to score-eligible cells (the only cells the vendor scores).
    This is the compact join the T1/T3 instruments need — a full month is
    ~1.3M rows, the target slice ~10-25% of that.

    The per-panel-month slice is cached as parquet under ``mleng/_cache/``
    on first build (one slow build, then seconds). Feb-2031 is guarded.
    """
    months = list(months)
    guard_no_feb(panel, months)
    cache = _cache_dir()
    frames = []
    keys = ["timestamp", "station_id", "link_id"]
    for m in months:
        cpath = cache / f"truth_targets_{panel}_{m}.parquet"
        if use_cache and cpath.exists():
            d = pd.read_parquet(cpath)
            d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
            frames.append(d)
            continue
        tmpl = task1_template(panel, use_cache=use_cache)
        tk = tmpl[tmpl["timestamp"].dt.strftime("%Y-%m") == m][
            keys + ["mask_regime"]].drop_duplicates()
        if tk.empty:
            continue
        st = load_mainline(panel, [m], columns=keys + [
            "speed_kmh", "flow_vph", "is_score_eligible"])
        st = st[st["is_score_eligible"].astype(bool)]
        d = tk.merge(st, on=keys, how="inner", validate="one_to_one")
        d = d[keys + ["mask_regime", "speed_kmh", "flow_vph"]]
        if use_cache:
            _write_cache_parquet(d, cpath)
        frames.append(d)
    if not frames:
        return pd.DataFrame(columns=keys + ["mask_regime", "speed_kmh", "flow_vph"])
    return pd.concat(frames, ignore_index=True)


def load_ramps(panel: str, months: Iterable[str],
               columns: Optional[list[str]] = None) -> pd.DataFrame:
    """Load ramp (on/off) detector states for a panel across months.

    A ramp record carries the measured count plus quality fields; there is no
    speed column (README). Memory-efficient column selection, same as
    :func:`load_mainline`.
    """
    months = list(months)
    guard_no_feb(panel, months)
    if panel not in PANELS:
        raise ValueError(f"unknown panel {panel!r}")
    frames = []
    for m in months:
        root = DATA_ROOT / "corridors" / panel / "train" / "ramp_states" / f"year_month={m}"
        if not root.exists():
            continue
        dataset = ds.dataset(str(root), format="parquet", partitioning="hive")
        df = dataset.to_table(columns=columns).to_pandas()
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out


# --------------------------------------------------------------------------
# Network topology
# --------------------------------------------------------------------------

def load_network(panel: str) -> dict[str, pd.DataFrame]:
    """Load the static network tables for a panel.

    Returns dict with keys: ``links`` (length, lanes, free speed, capacity),
    ``fd_parameters`` (fundamental-diagram params incl. ``v_cut`` where the
    release ships it), ``topology`` (link->link), ``ramp_map``,
    ``path_set``, ``path_incidence``, ``base_od`` (weak OD prior).
    """
    guard_no_feb(panel)
    net = DATA_ROOT / "corridors" / panel / "network"
    names = {
        "links": "links.csv",
        "fd_parameters": "fd_parameters.csv",
        "topology": "lwr_mainline_topology.csv",
        "ramp_map": "ramp_attachment_map.csv",
        "path_set": "path_set.csv",
        "path_incidence": "path_link_incidence.csv",
        "base_od": "base_od.csv",
    }
    out: dict[str, pd.DataFrame] = {}
    for key, fname in names.items():
        p = net / fname
        out[key] = pd.read_csv(p) if p.exists() else pd.DataFrame()
    return out


def station_lane_counts(panel: str) -> dict[str, float]:
    """Map (station_id, link_id) -> lane count, mirroring vendor logic.

    Vendor ``station_lanes`` reads lanes off links.csv keyed by station then
    link; replicate that here so lanes do not need the vendor import.
    """
    from task1.baseline_task1_historical_mean import station_lanes
    return station_lanes(DATA_ROOT / "corridors" / panel)


def queue_speed_thresholds(panel: str) -> dict[str, float]:
    """Per-link queue speed cutoffs: released ``v_cut`` with the vendor's
    ``0.6 * free_speed_kmh`` fallback. A cell is queued when
    ``speed_kmh < threshold``. (Vendored from task2/queue_utils.thresholds.)"""
    from task2.queue_utils import thresholds
    net = load_network(panel)
    links = net["links"]
    if links.empty:
        raise FileNotFoundError(f"no links.csv for panel {panel}")
    values, _source = thresholds(DATA_ROOT / "corridors" / panel, links)
    return values


# --------------------------------------------------------------------------
# Task templates / windows / OD artifacts (train split)
# --------------------------------------------------------------------------

def _date_from_filename(path: Path) -> Optional[str]:
    """Extract ``YYYY-MM-DD`` from release filenames like
    ``synthetic_mainline_2030_06_01.parquet``. Returns None when the name
    does not match."""
    m = re.match(r".*_(\d{4})_(\d{2})_(\d{2})\.parquet$", path.name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _cache_dir() -> Path:
    """Package-local cache for expensive one-time builds (templates, truth)."""
    d = Path(__file__).resolve().parent / "_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_cache_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write a cache parquet atomically (temp file + rename) so a killed
    process can never leave a half-written file behind."""
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def task1_template(panel: str, use_cache: bool = True) -> pd.DataFrame:
    """Task 1 train template: every scored (panel, timestamp, station, link,
    regime) target row. Filter to a pseudo-month with the ``timestamp``
    column; NEVER includes Feb-2031 in CV use.

    The raw CSV is ~2.8M rows; on first read it is converted to a parquet
    cache under the mleng package dir so later reads take seconds.
    """
    guard_no_feb(panel)
    cache = _cache_dir()
    cpath = cache / f"task1_template_{panel}.parquet"
    if use_cache and cpath.exists():
        d = pd.read_parquet(cpath)
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
        return d
    p = DATA_ROOT / "task1" / panel / "train" / "sample_submission_state.csv"
    d = pd.read_csv(p, dtype={"panel": str, "station_id": str, "link_id": str,
                              "mask_regime": str})
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    if use_cache:
        cache.mkdir(parents=True, exist_ok=True)
        _write_cache_parquet(d, cpath)
    return d


def task2_windows(panel: str) -> pd.DataFrame:
    """Task 2 train window index (10 windows per scored panel for the split:
    5 queue_onset + 5 queue_ongoing; all dated 2030-06 in this release)."""
    guard_no_feb(panel)
    p = DATA_ROOT / "task2" / panel / "train" / "window_index.csv"
    d = pd.read_csv(p, dtype={"window_id": str, "panel": str, "family_id": str,
                              "condition": str})
    for c in ("forecast_origin", "history_start", "history_end",
              "forecast_start", "forecast_end"):
        d[c] = pd.to_datetime(d[c], utc=True)
    return d


def task2_history(panel: str, window_ids: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Task 2 published 60-min window histories (raw observations).

    ``window_ids`` is pushed into the parquet scan so a lane only pays for
    the windows it needs.
    """
    guard_no_feb(panel, window_ids)
    p = DATA_ROOT / "task2" / panel / "train" / "window_history.parquet"
    if window_ids is not None:
        import pyarrow.compute as pc
        filt = pc.field("window_id").isin(list(window_ids))
        d = pq.read_table(p, filters=filt).to_pandas()
    else:
        d = pd.read_parquet(p)
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    return d


def task2_queue_template(panel: str) -> pd.DataFrame:
    """Task 2 train horizon template: (window_id, timestamp, link_id) cells."""
    guard_no_feb(panel)
    p = DATA_ROOT / "task2" / panel / "train" / "sample_submission_queue.csv"
    d = pd.read_csv(p, dtype={"window_id": str, "link_id": str})
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    return d


def task4_counts(panel: str) -> pd.DataFrame:
    """Released link counts for the train split (S_link truth)."""
    guard_no_feb(panel)
    p = DATA_ROOT / "task4" / panel / "train" / "synthetic_link_counts.csv"
    return pd.read_csv(p, dtype={"panel": str, "link_id": str})


def task4_prior(panel: str) -> pd.DataFrame:
    """Released weak OD prior for the train split (base_od-derived)."""
    guard_no_feb(panel)
    p = DATA_ROOT / "task4" / panel / "train" / "synthetic_weak_prior.csv"
    return pd.read_csv(p)


def od_operator(panel: str):
    """Path->link incidence operator for a panel.

    Returns ``(path_ids, link_ids, A, paths)`` reusing the vendor loader, so
    the lane-side math matches the scorer exactly. ``A`` is (n_links, n_paths).
    """
    guard_no_feb(panel)
    from task4.build_task4_odme_artifacts import load_operator
    return load_operator(DATA_ROOT / "corridors" / panel / "network")


# --------------------------------------------------------------------------
# 007D-style universe option
# --------------------------------------------------------------------------

def build_universe(states: pd.DataFrame,
                   dt_max_hours: float = UNIVERSE_DT_MAX_HOURS) -> dict:
    """Build a 007D-style spacetime universe over a mainline states frame.

    Conventions (EXP-007D discretization):
      * a *cell* is ``(timestamp, link_id)``;
      * a cell is *observable* iff ``is_score_eligible`` is true, i.e. every
        scored channel is present and ``pct_observed >= 75``;
      * a *transition* ``cell_t -> cell_{t+1}`` on the same link is observable
        iff both endpoints are observable and ``dt <= 5.1/60 hours``.

    Returns ``{"cells": DataFrame, "transitions": DataFrame}``. ``cells``
    carries ``observable``; ``transitions`` carries ``dt_hours`` and
    ``observable``. Pure function of its input — no month logic, so the
    Feb guard is the caller's (pass only guarded frames in).
    """
    need = {"timestamp", "link_id", "is_score_eligible"}
    missing = need - set(states.columns)
    if missing:
        raise ValueError(f"build_universe needs columns {sorted(need)}; missing {sorted(missing)}")
    cells = states[["timestamp", "link_id", "is_score_eligible"]].copy()
    cells["observable"] = cells["is_score_eligible"].astype(bool)
    cells = cells.drop(columns=["is_score_eligible"]).drop_duplicates(
        ["timestamp", "link_id"]).sort_values(["link_id", "timestamp"]).reset_index(drop=True)

    cells["_t_next"] = cells.groupby("link_id")["timestamp"].shift(-1)
    cells["_link_next"] = cells.groupby("link_id")["link_id"].shift(-1)
    cells["_obs_next"] = cells.groupby("link_id")["observable"].shift(-1)
    same = cells["_link_next"] == cells["link_id"]
    dt_h = (cells["_t_next"] - cells["timestamp"]).dt.total_seconds() / 3600.0
    transitions = pd.DataFrame({
        "link_id": cells["link_id"],
        "t_from": cells["timestamp"],
        "t_to": cells["_t_next"],
        "dt_hours": dt_h,
        "observable": (cells["observable"] & cells["_obs_next"].fillna(False).astype(bool)
                       & same.fillna(False) & (dt_h <= dt_max_hours)).fillna(False).astype(bool),
    })
    transitions = transitions.dropna(subset=["t_to"]).reset_index(drop=True)
    cells = cells.drop(columns=["_t_next", "_link_next", "_obs_next"])
    return {"cells": cells, "transitions": transitions,
            "dt_max_hours": dt_max_hours,
            "n_cells": len(cells), "n_observable_cells": int(cells["observable"].sum()),
            "n_transitions": len(transitions),
            "n_observable_transitions": int(transitions["observable"].sum())}
