"""
Collects every underlying table into a tidy {name: DataFrame} map for the
appendix, and provides CSV / multi-sheet Excel export helpers.
"""
from __future__ import annotations

import io
import re

import pandas as pd

from analysis import linkedin as L


def collect_tables(data: dict, ga4=None, merged: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    followers = data.get("followers")
    if followers:
        f = L.followers_summary(followers)
        if f:
            tables["LinkedIn — new followers (daily)"] = f["daily"]
        for name, _ in followers.demographics.items():
            df = L.demographic_table(followers, name, top=1000)
            if df is not None:
                tables[f"LinkedIn followers — {name.lower()}"] = df

    content = data.get("content")
    if content:
        c = L.content_summary(content)
        if c is not None:
            keep = [col for col in c["daily"].columns if not col.startswith("_")]
            tables["LinkedIn — content metrics (daily)"] = c["daily"][keep]
        pf = L._post_frame(content)
        if pf is not None:
            tables["LinkedIn — posts"] = pf

    visitors = data.get("visitors")
    if visitors:
        v = L.visitors_summary(visitors)
        if v is not None:
            tables["LinkedIn — page visitors (daily)"] = v["daily"]
        for name, _ in visitors.demographics.items():
            df = L.demographic_table(visitors, name, top=1000)
            if df is not None:
                tables[f"LinkedIn visitors — {name.lower()}"] = df

    if ga4 is not None:
        for attr, label in (
            ("timeseries", "GA4 — daily"),
            ("by_channel", "GA4 — by channel"),
            ("by_source_medium", "GA4 — by source/medium"),
            ("landing_pages", "GA4 — landing pages"),
            ("landing_sources", "GA4 — where visitors arrived (page × channel)"),
            ("top_pages", "GA4 — top pages"),
            ("by_country", "GA4 — by country"),
            ("by_device", "GA4 — by device"),
        ):
            df = getattr(ga4, attr, None)
            if df is not None and not df.empty:
                tables[label] = df

    if merged is not None and not merged.empty:
        tables["Cross-channel — aligned daily"] = merged

    return tables


def _sheet_name(name: str, used: set) -> str:
    """Excel sheet names: <=31 chars, no []:*?/\\, unique."""
    clean = re.sub(r"[\[\]:*?/\\]", "-", name)[:31]
    base, i = clean, 1
    while clean in used:
        suffix = f" {i}"
        clean = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(clean)
    return clean


def to_excel_bytes(tables: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    used: set = set()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in tables.items():
            df.to_excel(xw, sheet_name=_sheet_name(name, used), index=False)
    return buf.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
