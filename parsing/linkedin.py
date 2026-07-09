"""
Tolerant LinkedIn export parser.

LinkedIn company-page exports are messy: legacy binary .xls (needs xlrd) or
.xlsx (openpyxl), multi-sheet, sometimes with a title/metadata row sitting
*above* the real header row. This module:

  * reads either format from a path OR an uploaded buffer,
  * auto-detects which export it is (Visitors / Followers / Content /
    Competitors) from sheet names + header content,
  * finds the real header row dynamically (never hardcodes cell positions),
  * returns a normalized, typed result — and fails loudly, never silently
    returning an empty frame.

Nothing downstream should read raw cells; everything goes through here.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# Export kinds
FOLLOWERS = "followers"
VISITORS = "visitors"
CONTENT = "content"
COMPETITORS = "competitors"
UNKNOWN = "unknown"

KIND_LABELS = {
    FOLLOWERS: "Followers",
    VISITORS: "Visitors",
    CONTENT: "Content / Posts",
    COMPETITORS: "Competitors",
    UNKNOWN: "Unrecognized",
}


@dataclass
class ParsedLinkedIn:
    """Result of parsing one LinkedIn export file."""
    kind: str
    source_name: str
    sheets: dict[str, pd.DataFrame] = field(default_factory=dict)  # cleaned, header-applied
    time_series: Optional[pd.DataFrame] = None    # the main dated table (if any)
    demographics: dict[str, pd.DataFrame] = field(default_factory=dict)  # label/value tables
    posts: Optional[pd.DataFrame] = None          # per-post table (content only)
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    @property
    def date_range(self) -> Optional[tuple[pd.Timestamp, pd.Timestamp]]:
        ts = self.time_series
        if ts is not None and "Date" in ts.columns and ts["Date"].notna().any():
            return ts["Date"].min(), ts["Date"].max()
        return None


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _pick_engine(name: str) -> Optional[str]:
    n = (name or "").lower()
    if n.endswith(".xls"):
        return "xlrd"
    if n.endswith((".xlsx", ".xlsm")):
        return "openpyxl"
    return None  # let pandas guess


def _open_excel(source, source_name: str) -> pd.ExcelFile:
    """Open a path or an uploaded buffer, trying the right engine, then fallbacks."""
    engine = _pick_engine(source_name)
    data = source.read() if hasattr(source, "read") else None
    tried: list = []
    for eng in [engine, "xlrd", "openpyxl", None]:
        if eng in tried:
            continue
        tried.append(eng)
        try:
            buf = io.BytesIO(data) if data is not None else source
            return pd.ExcelFile(buf, engine=eng) if eng else pd.ExcelFile(buf)
        except Exception:
            continue
    raise ValueError(
        f"Could not open '{source_name}' as Excel. Is it a real LinkedIn .xls/.xlsx export?"
    )


def _find_header_row(raw: pd.DataFrame, max_scan: int = 15) -> int:
    """
    Find the first row that looks like a header: enough non-null cells, mostly
    strings, and followed by at least one data row. Handles the LinkedIn quirk
    where a title row sits above the real header.
    """
    ncols = max(raw.shape[1], 1)
    threshold = max(2, ncols * 0.5)
    n = min(len(raw), max_scan)
    for i in range(n):
        row = raw.iloc[i]
        non_null = int(row.notna().sum())
        if non_null < threshold:
            continue
        # header cells should be mostly text (labels), not numbers
        str_like = sum(isinstance(v, str) and v.strip() != "" for v in row)
        if str_like < max(2, non_null * 0.6):
            continue
        if i + 1 < len(raw):  # must have data beneath it
            return i
    return 0  # fall back to first row


def _clean_sheet(xl: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    """Read one sheet, locate its real header, apply it, drop empty rows/cols."""
    raw = xl.parse(sheet, header=None)
    if raw.empty:
        return raw
    hdr = _find_header_row(raw)
    df = xl.parse(sheet, header=hdr)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df.reset_index(drop=True)


def _coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Parse a 'Date' column (LinkedIn uses US MM/DD/YYYY) if present."""
    for col in df.columns:
        if str(col).strip().lower() == "date":
            df = df.rename(columns={col: "Date"})
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=False)
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
            break
    return df


def _numify(df: pd.DataFrame, skip: tuple[str, ...] = ("Date",)) -> pd.DataFrame:
    """Coerce non-date columns to numeric where possible (leaves text alone)."""
    for col in df.columns:
        if col in skip:
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().mean() >= 0.5:  # only if it really looks numeric
            df[col] = converted
    return df


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def _detect_kind(sheet_names: list[str], sheets: dict[str, pd.DataFrame]) -> str:
    names = {s.lower() for s in sheet_names}
    all_cols = " ".join(str(c).lower() for df in sheets.values() for c in df.columns)

    if any("new followers" in n or n == "followers" for n in names):
        return FOLLOWERS
    if any("visitor" in n for n in names):
        return VISITORS
    if {"metrics", "all posts"} & names or ("impressions" in all_cols and "post" in all_cols):
        return CONTENT
    if any("competitor" in n for n in names) or "competitor" in all_cols:
        return COMPETITORS

    # fallbacks by column content
    if "impressions" in all_cols and ("reactions" in all_cols or "engagement rate" in all_cols):
        return CONTENT
    if "total followers" in all_cols:
        return FOLLOWERS
    if "total views" in all_cols or "page view" in all_cols:
        return VISITORS
    return UNKNOWN


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse_linkedin(source, source_name: Optional[str] = None) -> ParsedLinkedIn:
    """
    Parse a LinkedIn export from a file path or an uploaded buffer.
    `source_name` is used for engine/type detection when `source` is a buffer.
    """
    if source_name is None:
        source_name = getattr(source, "name", str(source))

    xl = _open_excel(source, source_name)
    raw_sheets = {s: _clean_sheet(xl, s) for s in xl.sheet_names}
    raw_sheets = {s: df for s, df in raw_sheets.items() if not df.empty}
    if not raw_sheets:
        raise ValueError(f"'{source_name}' opened but every sheet was empty.")

    kind = _detect_kind(list(raw_sheets.keys()), raw_sheets)
    result = ParsedLinkedIn(kind=kind, source_name=source_name)

    for name, df in raw_sheets.items():
        df = _coerce_dates(df)
        df = _numify(df)
        result.sheets[name] = df

        low = name.lower()
        cols_low = " ".join(map(str, df.columns)).lower()
        has_date = "Date" in df.columns
        if has_date and result.time_series is None:
            result.time_series = df
        elif kind == CONTENT and ("post" in low or "post title" in cols_low):
            result.posts = df
        elif not has_date and df.shape[1] <= 3 and len(df) >= 1:
            result.demographics[name] = df

    if kind == UNKNOWN:
        result.warnings.append(
            f"Could not confidently classify '{source_name}'. "
            f"Sheets found: {list(raw_sheets.keys())}."
        )
    if kind in (FOLLOWERS, VISITORS, CONTENT) and result.time_series is None:
        result.warnings.append(
            f"No dated time-series table found in '{source_name}' — "
            f"trends over time will be unavailable for this file."
        )
    return result
