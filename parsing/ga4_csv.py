"""
Tolerant parser for manual GA4 CSV / Excel exports (the fallback when the live
Data API isn't connected).

GA4 UI exports are messy: CSVs carry `#`-comment metadata blocks and often
several tables separated by blank lines; Excel exports put each table on its own
sheet with the header a few rows down. This maps whatever it finds onto the same
normalized `GA4Data` shape the live connector produces, so the analysis/view
layers are source-agnostic.
"""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd

from connectors.ga4 import GA4Data
from parsing.linkedin import _find_header_row  # reuse the header detector

# GA4 UI metric labels -> canonical names used across the app
_METRIC_MAP = {
    "totalUsers": ("total users", "active users", "users"),
    "newUsers": ("new users",),
    "sessions": ("sessions",),
    "engagedSessions": ("engaged sessions",),
    "engagementRate": ("engagement rate",),
    "averageSessionDuration": ("average session duration", "average engagement time",
                               "avg engagement time"),
    "screenPageViews": ("screen page views", "page views", "views"),
    "keyEvents": ("key events", "conversions"),
}
# Dimension first-column label -> GA4Data slot
_DIM_SLOTS = {
    "by_channel": ("channel",),
    "by_source_medium": ("source", "medium"),
    "landing_pages": ("landing page",),
    "top_pages": ("page path", "page title", "page and screen", "page"),
    "by_country": ("country",),
    "by_device": ("device",),
}


def _canon_metric(colname: str) -> Optional[str]:
    """Map a GA4 label to a canonical metric by the LONGEST matching rule, so
    'Engaged sessions' beats 'sessions' and 'New users' beats 'users'."""
    cl = str(colname).strip().lower()
    best, best_len = None, 0
    for canon, needles in _METRIC_MAP.items():
        for n in needles:
            if n in cl and len(n) > best_len:
                best, best_len = canon, len(n)
    return best


def _rename_metrics(df: pd.DataFrame) -> pd.DataFrame:
    ren = {}
    for c in df.columns:
        canon = _canon_metric(c)
        if canon and canon not in ren.values():
            ren[c] = canon
    df = df.rename(columns=ren)
    for c in df.columns:
        if c in _METRIC_MAP:  # numeric-ify metric columns
            df[c] = pd.to_numeric(
                df[c].astype(str).str.replace(",", "").str.replace("%", ""), errors="coerce"
            )
            if "rate" in c.lower() and df[c].max(skipna=True) and df[c].max() > 1.5:
                df[c] = df[c] / 100.0  # percent -> fraction
    return df


def _find_date_col(df: pd.DataFrame) -> Optional[str]:
    for c in df.columns:
        if "date" in str(c).strip().lower():
            return c
    return None


def _classify_and_store(df: pd.DataFrame, data: GA4Data):
    if df is None or df.empty:
        return
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return
    df.columns = [str(c).strip() for c in df.columns]

    date_col = _find_date_col(df)
    if date_col:
        df = _rename_metrics(df).rename(columns={date_col: "date"})
        df["date"] = pd.to_datetime(df["date"].astype(str).str.replace(r"\.0$", "", regex=True),
                                    format="%Y%m%d", errors="coerce")
        if df["date"].isna().all():  # not YYYYMMDD — try generic
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if not df.empty and data.timeseries is None:
            data.timeseries = df
            return

    # dimension table — route by its first-column label
    first = str(df.columns[0]).lower()
    df = _rename_metrics(df)
    for slot, needles in _DIM_SLOTS.items():
        if any(n in first for n in needles) and getattr(data, slot) is None:
            setattr(data, slot, df.reset_index(drop=True))
            return
    data.warnings.append(f"Unmapped table with columns {list(df.columns)[:4]} — kept out of views.")


def _parse_csv_blocks(raw: bytes) -> list[pd.DataFrame]:
    text = raw.decode("utf-8-sig", errors="replace")
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith("#"):          # GA4 metadata comment
            continue
        if line.strip() == "":            # blank line separates tables
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))

    frames = []
    for b in blocks:
        try:
            frames.append(pd.read_csv(io.StringIO(b)))
        except Exception:
            continue
    return frames


def parse_ga4_export(source, source_name: Optional[str] = None) -> GA4Data:
    if source_name is None:
        source_name = getattr(source, "name", str(source))
    data = GA4Data(source="csv")

    name = source_name.lower()
    raw = source.read() if hasattr(source, "read") else open(source, "rb").read()

    if name.endswith(".csv"):
        for df in _parse_csv_blocks(raw):
            _classify_and_store(df, data)
    else:  # Excel: each sheet is a candidate table
        xl = pd.ExcelFile(io.BytesIO(raw))
        for sheet in xl.sheet_names:
            rawdf = xl.parse(sheet, header=None)
            if rawdf.empty:
                continue
            hdr = _find_header_row(rawdf)
            _classify_and_store(xl.parse(sheet, header=hdr), data)

    if data.timeseries is not None and not data.timeseries.empty:
        ts = data.timeseries
        data.start = ts["date"].min().date()
        data.end = ts["date"].max().date()
    else:
        data.warnings.append(
            f"No dated table found in '{source_name}'. Export a report that includes a "
            "Date dimension for trend charts."
        )
    return data
