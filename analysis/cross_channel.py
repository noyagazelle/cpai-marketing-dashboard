"""
Cross-channel analysis — does LinkedIn activity actually move the needle?

Builds one aligned daily table from whatever is loaded, then computes:
  * correlations between LinkedIn activity (impressions, engagement, posting)
    and downstream traffic (LinkedIn page visits, and — when GA4 is connected —
    website social-referral sessions and conversions);
  * post-day lift: average outcome on days we posted vs days we didn't.

Everything degrades gracefully: with only LinkedIn exports we can still relate
content activity to LinkedIn page visits; GA4 unlocks the website link.
Correlation is reported with its sample size and labelled directional for small n.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from analysis import linkedin as L

# Human labels for the daily columns we may assemble
COL_LABELS = {
    "li_impressions": "LinkedIn impressions",
    "li_engagements": "LinkedIn engagements",
    "li_posts": "Posts published",
    "li_page_views": "LinkedIn page views",
    "li_new_followers": "New followers",
    "ga4_sessions": "Website sessions",
    "ga4_key_events": "Website key events",
    "social_sessions": "Website social-referral sessions",
    "social_key_events": "Social-referral key events",
}


def build_daily(data: dict, ga4=None) -> pd.DataFrame:
    """Merge all available daily series onto a single date index."""
    frames = []

    content = data.get("content")
    if content:
        c = L.content_summary(content)
        if c is not None:
            df = c["daily"][["Date", "_impressions", "_engagements"]].rename(
                columns={"Date": "date", "_impressions": "li_impressions",
                         "_engagements": "li_engagements"})
            frames.append(df.set_index("date"))
        pf = L._post_frame(content)
        if pf is not None and "Created" in pf.columns and pf["Created"].notna().any():
            pc = (pf.dropna(subset=["Created"])
                  .groupby(pf["Created"].dt.normalize()).size().rename("li_posts"))
            pc.index.name = "date"
            frames.append(pc.to_frame())

    visitors = data.get("visitors")
    if visitors:
        v = L.visitors_summary(visitors)
        if v is not None and v["pv_col"]:
            df = v["daily"][["Date", v["pv_col"]]].rename(
                columns={"Date": "date", v["pv_col"]: "li_page_views"})
            frames.append(df.set_index("date"))

    followers = data.get("followers")
    if followers:
        f = L.followers_summary(followers)
        if f is not None:
            df = f["daily"][["Date", "New followers"]].rename(
                columns={"Date": "date", "New followers": "li_new_followers"})
            frames.append(df.set_index("date"))

    ga4_span = None
    ga4_count_cols: list[str] = []
    if ga4 is not None and ga4.timeseries is not None and not ga4.timeseries.empty:
        g = ga4.timeseries.copy().set_index("date")
        ga4_span = (g.index.min(), g.index.max())
        for src, dst in (("sessions", "ga4_sessions"), ("keyEvents", "ga4_key_events")):
            if src in g.columns:
                frames.append(g[[src]].rename(columns={src: dst}))
                ga4_count_cols.append(dst)
        if getattr(ga4, "social_timeseries", None) is not None and not ga4.social_timeseries.empty:
            s = ga4.social_timeseries.copy().set_index("date")
            frames.append(s)
            ga4_count_cols += [c for c in s.columns]

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, axis=1).sort_index()
    if "li_posts" in merged.columns:
        merged["li_posts"] = merged["li_posts"].fillna(0)
    # GA4 only returns rows for days that had activity, so quiet days come back as
    # NaN and break the chart lines. Within the GA4 window, a missing day = 0.
    if ga4_span and ga4_count_cols:
        within = (merged.index >= ga4_span[0]) & (merged.index <= ga4_span[1])
        for c in ga4_count_cols:
            if c in merged.columns:
                merged.loc[within, c] = merged.loc[within, c].fillna(0)
    return merged.reset_index().rename(columns={"index": "date"})


def _strength(r: float) -> str:
    a = abs(r)
    if a >= 0.7:
        return "strong"
    if a >= 0.4:
        return "moderate"
    if a >= 0.2:
        return "weak"
    return "negligible"


def correlations(merged: pd.DataFrame) -> list[dict]:
    """Pearson r for the driver→outcome pairs we care about (where both exist)."""
    if merged is None or merged.empty:
        return []
    pairs = [
        ("li_impressions", "li_page_views"),
        ("li_engagements", "li_page_views"),
        ("li_impressions", "social_sessions"),
        ("li_engagements", "social_sessions"),
        ("li_posts", "social_sessions"),
        ("li_impressions", "ga4_sessions"),
        ("li_engagements", "ga4_key_events"),
        ("li_impressions", "li_new_followers"),
    ]
    out = []
    for x, y in pairs:
        if x not in merged.columns or y not in merged.columns:
            continue
        sub = merged[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < 7 or sub[x].std() == 0 or sub[y].std() == 0:
            continue
        r = float(np.corrcoef(sub[x], sub[y])[0, 1])
        if np.isnan(r):
            continue
        out.append({
            "x": x, "y": y, "x_label": COL_LABELS.get(x, x), "y_label": COL_LABELS.get(y, y),
            "r": r, "n": len(sub), "strength": _strength(r),
            "directional": len(sub) < 14,
        })
    return sorted(out, key=lambda d: abs(d["r"]), reverse=True)


def post_day_lift(merged: pd.DataFrame, target: str) -> Optional[dict]:
    """Average `target` on days with a post vs days without."""
    if merged is None or merged.empty or "li_posts" not in merged.columns or target not in merged.columns:
        return None
    sub = merged[["li_posts", target]].copy()
    sub[target] = pd.to_numeric(sub[target], errors="coerce")
    sub = sub.dropna(subset=[target])
    post = sub[sub["li_posts"] > 0][target]
    non = sub[sub["li_posts"] == 0][target]
    if len(post) < 2 or len(non) < 2:
        return None
    lift = (post.mean() - non.mean()) / non.mean() if non.mean() else None
    return {
        "target": target, "target_label": COL_LABELS.get(target, target),
        "post_avg": float(post.mean()), "nonpost_avg": float(non.mean()),
        "lift": lift, "n_post": int(len(post)), "n_nonpost": int(len(non)),
    }
