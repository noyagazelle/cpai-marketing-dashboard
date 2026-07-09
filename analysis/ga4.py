"""
GA4 analysis — turns a normalized GA4Data into KPIs, deltas, and rankings.

Source-agnostic: if the connector supplied accurate `totals`/`prev_totals`
(live API), we use them. Otherwise (CSV fallback) we aggregate the timeseries
and derive a recent-vs-prior split, exactly like the LinkedIn side — and flag
that summed users are approximate.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from analysis.linkedin import pct_delta, split_half

# additive metrics can be summed across days; rates/durations cannot
_ADDITIVE = {"totalUsers", "newUsers", "sessions", "engagedSessions",
             "screenPageViews", "keyEvents"}
_LABELS = {
    "totalUsers": "Users", "newUsers": "New users", "sessions": "Sessions",
    "engagedSessions": "Engaged sessions", "engagementRate": "Engagement rate",
    "averageSessionDuration": "Avg engagement time", "screenPageViews": "Page views",
    "keyEvents": "Key events",
}


def _agg_timeseries(ts: pd.DataFrame) -> dict:
    out = {}
    if ts is None or ts.empty:
        return out
    for m in _ADDITIVE:
        if m in ts.columns:
            out[m] = float(pd.to_numeric(ts[m], errors="coerce").sum())
    # engagement rate: prefer engaged/total sessions; else mean
    if "engagedSessions" in ts.columns and "sessions" in ts.columns and out.get("sessions"):
        out["engagementRate"] = out["engagedSessions"] / out["sessions"]
    elif "engagementRate" in ts.columns:
        out["engagementRate"] = float(pd.to_numeric(ts["engagementRate"], errors="coerce").mean())
    # avg engagement time: sessions-weighted mean if possible
    if "averageSessionDuration" in ts.columns:
        d = pd.to_numeric(ts["averageSessionDuration"], errors="coerce")
        if "sessions" in ts.columns:
            w = pd.to_numeric(ts["sessions"], errors="coerce")
            out["averageSessionDuration"] = float((d * w).sum() / w.sum()) if w.sum() else float(d.mean())
        else:
            out["averageSessionDuration"] = float(d.mean())
    return out


def summarize(data) -> dict:
    """Return {metric: {value, delta, label, context}} plus notes."""
    notes = list(data.warnings)
    ts = data.timeseries

    if data.totals:                       # live API — accurate
        cur = data.totals
        prev = data.prev_totals or {}
        deltas = {m: pct_delta(cur.get(m), prev.get(m)) for m in cur}
        ctx = "vs previous period"
    else:                                 # CSV fallback — aggregate + split-half
        cur = _agg_timeseries(ts)
        deltas, ctx = {}, ""
        if ts is not None and not ts.empty:
            for m in cur:
                if m in _ADDITIVE and m in ts.columns:
                    sp = split_half(ts.set_index("date")[m])
                    if sp.get("available"):
                        deltas[m] = sp["delta"]
                        ctx = f"last {sp['half_days']}d vs prior {sp['half_days']}d"
        if any(m in cur for m in ("totalUsers", "newUsers")):
            notes.append("Totals for users are summed across days (CSV export) and are approximate; "
                         "connect the live API for de-duplicated unique users.")

    kpis = {}
    for m, v in cur.items():
        kpis[m] = {"value": v, "delta": deltas.get(m), "label": _LABELS.get(m, m), "context": ctx}
    return {"kpis": kpis, "notes": notes,
            "order": ["totalUsers", "newUsers", "sessions", "engagementRate",
                      "averageSessionDuration", "keyEvents", "screenPageViews"]}


def top_table(df: Optional[pd.DataFrame], dim: str, metric: str, n: int = 10) -> Optional[pd.DataFrame]:
    if df is None or df.empty or metric not in df.columns:
        return None
    d = df.copy()
    d[metric] = pd.to_numeric(d[metric], errors="coerce")
    return d.sort_values(metric, ascending=False).head(n).reset_index(drop=True)


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None or pd.isna(seconds):
        return "—"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"
