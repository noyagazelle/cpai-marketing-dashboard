"""
GA4 Data API connector.

Live path: authenticate with a service account and run reports against a GA4
property. Fallback path (parsing/ga4_csv.py) handles manual CSV/Excel exports.

Design goals
------------
* Import cleanly even when credentials are absent — the app must boot without GA4.
* Fail loudly with a human-readable message; never silently return empty data.
* Return the same normalized `GA4Data` shape regardless of source, so the
  analysis/view layers don't care whether data came from the API or a CSV.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

import config

# ---- Report definitions: (dimensions, metrics) we pull from GA4 --------------
# Chosen to cover the "website deep dive" + cross-channel needs.
TS_METRICS = ["totalUsers", "newUsers", "sessions", "engagedSessions",
              "engagementRate", "averageSessionDuration", "screenPageViews", "keyEvents"]


@dataclass
class GA4Data:
    """Normalized GA4 result — same shape from API or CSV fallback."""
    source: str                                   # "api" | "csv" | ...
    start: Optional[date] = None
    end: Optional[date] = None
    timeseries: Optional[pd.DataFrame] = None     # by date
    social_timeseries: Optional[pd.DataFrame] = None  # daily social sessions (cross-channel)
    by_channel: Optional[pd.DataFrame] = None     # sessionDefaultChannelGroup
    by_source_medium: Optional[pd.DataFrame] = None
    landing_pages: Optional[pd.DataFrame] = None
    landing_sources: Optional[pd.DataFrame] = None  # page × channel (where visitors arrived from)
    top_pages: Optional[pd.DataFrame] = None
    by_country: Optional[pd.DataFrame] = None
    by_device: Optional[pd.DataFrame] = None
    totals: dict = field(default_factory=dict)
    prev_totals: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Connection status (used by the UI to decide what to show)
# --------------------------------------------------------------------------- #
def status() -> dict:
    pid = config.ga4_property_id()
    creds_path = config.ga4_credentials_path()
    creds_info = config.ga4_credentials_info()
    have_creds = bool(creds_path or creds_info)
    if pid and have_creds:
        return {"configured": True, "property_id": pid,
                "reason": "Service account + property ID found."}
    missing = []
    if not pid:
        missing.append("GA4_PROPERTY_ID")
    if not have_creds:
        missing.append("GA4_SERVICE_ACCOUNT_JSON")
    return {"configured": False, "property_id": pid,
            "reason": f"Missing: {', '.join(missing)}."}


# --------------------------------------------------------------------------- #
# Live API
# --------------------------------------------------------------------------- #
def _client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account

    info = config.ga4_credentials_info()
    path = config.ga4_credentials_path()
    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
    if info:
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    elif path:
        creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    else:
        raise RuntimeError("No GA4 credentials configured.")
    return BetaAnalyticsDataClient(credentials=creds)


def _report_to_df(resp, dim_names: list[str], metric_names: list[str]) -> pd.DataFrame:
    rows = []
    for r in resp.rows:
        row = {d: r.dimension_values[i].value for i, d in enumerate(dim_names)}
        for j, m in enumerate(metric_names):
            raw = r.metric_values[j].value
            try:
                row[m] = float(raw)
            except (TypeError, ValueError):
                row[m] = raw
        rows.append(row)
    df = pd.DataFrame(rows)
    if "date" in df.columns and not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)
    return df


def _run(client, pid, dims, metrics, start: date, end: date, limit: int = 100000):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )
    req = RunReportRequest(
        property=f"properties/{pid}",
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=str(start), end_date=str(end))],
        limit=limit,
    )
    resp = client.run_report(req)
    return _report_to_df(resp, dims, metrics)


def _totals(client, pid, start: date, end: date) -> dict:
    df = _run(client, pid, [], TS_METRICS, start, end)
    if df.empty:
        return {}
    return {m: float(df.iloc[0][m]) for m in TS_METRICS if m in df.columns}


def fetch(start: date, end: date, prev_start: date, prev_end: date) -> GA4Data:
    """Pull the full GA4 report set for the given window (+ previous window totals)."""
    pid = config.ga4_property_id()
    if not pid:
        raise RuntimeError("GA4_PROPERTY_ID not set.")
    client = _client()

    data = GA4Data(source="api", start=start, end=end)
    data.timeseries = _run(client, pid, ["date"], TS_METRICS, start, end)
    data.by_channel = _run(client, pid, ["sessionDefaultChannelGroup"],
                           ["sessions", "totalUsers", "engagementRate", "keyEvents"], start, end)

    # Daily social sessions — powers the cross-channel (LinkedIn → website) analysis
    ch_ts = _run(client, pid, ["date", "sessionDefaultChannelGroup"],
                 ["sessions", "keyEvents"], start, end)
    if not ch_ts.empty:
        mask = ch_ts["sessionDefaultChannelGroup"].astype(str).str.contains("social", case=False, na=False)
        soc = (ch_ts[mask].groupby("date", as_index=False)[["sessions", "keyEvents"]].sum()
               .rename(columns={"sessions": "social_sessions", "keyEvents": "social_key_events"}))
        data.social_timeseries = soc
    data.by_source_medium = _run(client, pid, ["sessionSource", "sessionMedium"],
                                 ["sessions", "totalUsers", "keyEvents"], start, end)
    data.landing_pages = _run(client, pid, ["landingPage"],
                              ["sessions", "engagementRate", "keyEvents"], start, end)
    # Where visitors arrived from, per page (landing page × channel).
    data.landing_sources = _run(client, pid, ["landingPage", "sessionDefaultChannelGroup"],
                                ["sessions", "keyEvents"], start, end)
    data.top_pages = _run(client, pid, ["pagePath"], ["screenPageViews", "totalUsers"], start, end)
    data.by_country = _run(client, pid, ["country"], ["totalUsers", "sessions"], start, end)
    data.by_device = _run(client, pid, ["deviceCategory"], ["totalUsers", "sessions"], start, end)

    data.totals = _totals(client, pid, start, end)
    try:
        data.prev_totals = _totals(client, pid, prev_start, prev_end)
    except Exception as e:
        data.warnings.append(f"Could not fetch previous-period totals: {e}")
    return data
