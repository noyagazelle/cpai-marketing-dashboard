"""
Per-category period-over-period changes — e.g. how many followers each
seniority level gained/lost vs the previous saved period, or how sessions from
each channel moved for a landing page. Pure pandas; no Streamlit.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from analysis import linkedin as L


def change_table(cur: pd.DataFrame, prev: Optional[pd.DataFrame], label_col: str,
                 value_col: str, top: Optional[int] = None) -> Optional[pd.DataFrame]:
    """[label, Now, Previous, Change, % change, Trend] — one row per category in
    either period (missing in one period counts as 0). Sorted by current value."""
    if cur is None or cur.empty or prev is None or prev.empty:
        return None

    def _agg(df):
        d = df[[label_col, value_col]].copy()
        d[label_col] = d[label_col].astype(str).str.strip()
        d[value_col] = pd.to_numeric(d[value_col], errors="coerce").fillna(0)
        return d.groupby(label_col)[value_col].sum()

    now, before = _agg(cur), _agg(prev)
    out = pd.DataFrame({"Now": now, "Previous": before}).fillna(0)
    out["Change"] = out["Now"] - out["Previous"]
    out["% change"] = out.apply(
        lambda r: r["Change"] / r["Previous"] if r["Previous"] else None, axis=1)
    out["Trend"] = out["Change"].map(lambda c: "▲ Up" if c > 0 else ("▼ Down" if c < 0 else "= Same"))
    out = out.sort_values(["Now", "Previous"], ascending=False)
    out = out.rename_axis(label_col).reset_index()
    return out.head(top).reset_index(drop=True) if top else out


def cadence_change(res, prev_res) -> Optional[dict]:
    """Posting volume this period vs the previous saved period's content export.
    Posts/week is normalised by each export's own date range, so periods of
    different lengths compare fairly. None when either period has no posts."""
    if prev_res is None:
        return None
    now, before = L.cadence(res), L.cadence(prev_res)
    if not now or not before:
        return None

    def _weeks(r, cad):
        if r.date_range:
            return ((r.date_range[1] - r.date_range[0]).days + 1) / 7
        return cad["span_days"] / 7

    pw_now = now["n_posts"] / _weeks(res, now)
    pw_prev = before["n_posts"] / _weeks(prev_res, before)
    weekday = change_table(now["by_weekday"], before["by_weekday"], "Weekday", "Posts")
    order = list(now["by_weekday"]["Weekday"])
    weekday = weekday.set_index("Weekday").reindex(order).reset_index()
    return {
        "posts_now": now["n_posts"], "posts_prev": before["n_posts"],
        "per_week_now": round(pw_now, 1), "per_week_prev": round(pw_prev, 1),
        "per_week_delta": L.pct_delta(pw_now, pw_prev),
        "posts_delta": L.pct_delta(now["n_posts"], before["n_posts"]),
        "by_weekday": weekday,
    }


def excluded_note(res, prev_res, name: str) -> Optional[str]:
    """One-line note for groups hidden by L.EXCLUDED_GROUPS, e.g. "Bogotá … — 2,244
    (17% of all) ▲ +5 vs previous period". None when nothing is hidden."""
    ex = L.excluded_rows(res, name)
    if ex is None:
        return None
    prev_ex = L.excluded_rows(prev_res, name) if prev_res is not None else None
    prev_vals = (dict(zip(prev_ex.iloc[:, 0].astype(str).str.strip(), prev_ex.iloc[:, 1]))
                 if prev_ex is not None else {})
    parts = []
    for _, r in ex.iterrows():
        label, val = str(r.iloc[0]).strip(), r.iloc[1]
        txt = f"**{label}** — {val:,.0f} ({r['share']:.0%} of all)"
        if label in prev_vals:
            ch = val - prev_vals[label]
            arrow = "▲" if ch > 0 else ("▼" if ch < 0 else "=")
            txt += f", {arrow} {ch:+,.0f} vs previous period"
        parts.append(txt)
    return "; ".join(parts)


def demographic_change(res, prev_res, name: str, top: int = 10) -> Optional[pd.DataFrame]:
    """change_table for one LinkedIn demographic (e.g. "Seniority") across two periods."""
    if prev_res is None or name not in getattr(prev_res, "demographics", {}):
        return None
    cur = L.demographic_table(res, name, top=100000)
    prev = L.demographic_table(prev_res, name, top=100000)
    if cur is None or prev is None:
        return None
    # both tables are [label, value, share]; align on a common label/value name
    cur = cur.iloc[:, :2].set_axis([name, "value"], axis=1)
    prev = prev.iloc[:, :2].set_axis([name, "value"], axis=1)
    return change_table(cur, prev, name, "value", top=top)
