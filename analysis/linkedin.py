"""
Deterministic LinkedIn analytics.

Every number the dashboard shows is computed here from the parsed exports —
no estimates are invented, and where the data can't support a figure we return
None and let the UI say so. The AI/narrative layer (later) only describes
numbers produced here.

Key conventions
---------------
* LinkedIn's Followers "Total followers" daily column is NEW followers that day
  (sponsored + organic + auto-invited), NOT a running total. We treat it as such.
* Engagement (content) is defined explicitly as clicks + reactions + comments +
  reposts, and engagement rate = engagements / impressions. We also surface
  LinkedIn's own per-day "Engagement rate (total)" for reference.
* Period-over-period uses a split-half comparison of the loaded window
  (recent half vs prior half) — honest and clearly labelled, given the exports
  are typically a single ~30-day window.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def find_col(df: pd.DataFrame, *needles: str, exclude: tuple[str, ...] = ()) -> Optional[str]:
    """First column whose lowercased name contains all needles and none of exclude."""
    for c in df.columns:
        cl = str(c).lower()
        if all(n.lower() in cl for n in needles) and not any(e.lower() in cl for e in exclude):
            return c
    return None


def pct_delta(current: float, previous: float) -> Optional[float]:
    if previous in (0, None) or pd.isna(previous):
        return None
    return (current - previous) / abs(previous)


def split_half(series: pd.Series) -> dict:
    """
    Compare the recent half of a time-ordered series to the prior half.
    Returns sums, the delta, and the half-size so the UI can label it honestly.
    """
    s = series.dropna().reset_index(drop=True)
    n = len(s)
    if n < 4:
        return {"available": False, "n": n}
    half = n // 2
    prior = s.iloc[:half].sum()
    recent = s.iloc[-half:].sum()
    return {
        "available": True,
        "half_days": half,
        "recent": float(recent),
        "prior": float(prior),
        "delta": pct_delta(recent, prior),
    }


# --------------------------------------------------------------------------- #
# Followers
# --------------------------------------------------------------------------- #
def followers_summary(res, known_total: Optional[int] = None, prev_res=None) -> Optional[dict]:
    ts = res.time_series
    if ts is None or "Date" not in ts.columns:
        return None
    total_c = find_col(ts, "total", "follower")
    org_c = find_col(ts, "organic")
    spon_c = find_col(ts, "sponsored")
    auto_c = find_col(ts, "auto")

    daily = ts.copy()
    daily["_new"] = daily[total_c] if total_c else daily[[c for c in (org_c, spon_c, auto_c) if c]].sum(axis=1)
    daily["_cumulative"] = daily["_new"].cumsum()

    # Demographic-sum estimate (a LOWER bound — only counts followers whose
    # attribute is filled in, so it undercounts the true total).
    demo_est = None
    for name, d in res.demographics.items():
        valcol = d.columns[-1]
        vals = pd.to_numeric(d[valcol], errors="coerce")
        if vals.notna().any():
            demo_est = max(demo_est or 0, int(vals.sum()))

    # Prefer the actual total the user supplied; fall back to the estimate.
    audience = int(known_total) if known_total else demo_est
    audience_is_known = bool(known_total)

    new_total = int(daily["_new"].sum())
    growth_rate = None
    if audience and audience > new_total:
        # new followers as % of the pre-period base
        growth_rate = new_total / (audience - new_total)

    # True period-over-period vs the previous stored period (if provided)
    pop_new_delta = None
    if prev_res is not None:
        pprev = followers_summary(prev_res)
        if pprev:
            pop_new_delta = pct_delta(new_total, pprev["new_total"])

    return {
        "daily": daily[["Date", "_new", "_cumulative"]].rename(
            columns={"_new": "New followers", "_cumulative": "Cumulative (period)"}
        ),
        "new_total": new_total,
        "organic": int(daily[org_c].sum()) if org_c else None,
        "sponsored": int(daily[spon_c].sum()) if spon_c else None,
        "auto_invited": int(daily[auto_c].sum()) if auto_c else None,
        "avg_daily": round(daily["_new"].mean(), 1),
        "best_day": (daily.loc[daily["_new"].idxmax(), "Date"], int(daily["_new"].max())),
        "audience_estimate": audience,
        "audience_is_known": audience_is_known,
        "audience_demo_estimate": demo_est,
        "growth_rate": growth_rate,
        "pop_new_delta": pop_new_delta,
        "split": split_half(daily.set_index("Date")["_new"]),
        "source_split_cols": {"organic": org_c, "sponsored": spon_c, "auto_invited": auto_c},
    }


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
def content_summary(res, prev_res=None) -> Optional[dict]:
    ts = res.time_series
    if ts is None or "Date" not in ts.columns:
        return None
    imp_c = find_col(ts, "impressions", "total", exclude=("unique",))
    clk_c = find_col(ts, "clicks", "total")
    rea_c = find_col(ts, "reactions", "total")
    com_c = find_col(ts, "comments", "total")
    rep_c = find_col(ts, "reposts", "total")
    er_c = find_col(ts, "engagement rate", "total")

    daily = ts.copy()
    eng_cols = [c for c in (clk_c, rea_c, com_c, rep_c) if c]
    daily["_engagements"] = daily[eng_cols].sum(axis=1) if eng_cols else 0
    daily["_impressions"] = daily[imp_c] if imp_c else 0

    tot_imp = int(daily["_impressions"].sum())
    tot_eng = int(daily["_engagements"].sum())
    agg_er = (tot_eng / tot_imp) if tot_imp else None

    pop_imp_delta = pop_eng_delta = None
    if prev_res is not None:
        pc = content_summary(prev_res)
        if pc:
            pop_imp_delta = pct_delta(tot_imp, pc["total_impressions"])
            pop_eng_delta = pct_delta(tot_eng, pc["total_engagements"])

    return {
        "daily": daily,
        "impressions_col": imp_c,
        "er_col": er_c,
        "total_impressions": tot_imp,
        "total_engagements": tot_eng,
        "pop_impressions_delta": pop_imp_delta,
        "pop_engagements_delta": pop_eng_delta,
        "total_reactions": int(daily[rea_c].sum()) if rea_c else None,
        "total_comments": int(daily[com_c].sum()) if com_c else None,
        "total_reposts": int(daily[rep_c].sum()) if rep_c else None,
        "total_clicks": int(daily[clk_c].sum()) if clk_c else None,
        "agg_engagement_rate": agg_er,
        "split_impressions": split_half(daily.set_index("Date")["_impressions"]),
        "split_engagements": split_half(daily.set_index("Date")["_engagements"]),
    }


def _post_frame(res) -> Optional[pd.DataFrame]:
    posts = res.posts
    if posts is None or posts.empty:
        return None
    df = posts.copy()
    # normalize the columns we rely on
    ren = {}
    for want, needles in {
        "Title": ("post title",), "Type": ("post type",), "Author": ("posted by",),
        "Created": ("created date",), "Impressions": ("impressions",),
        "Clicks": ("clicks",), "CTR": ("click through",), "Likes": ("likes",),
        "Comments": ("comments",), "Reposts": ("reposts",),
        "EngRate": ("engagement rate",), "ContentType": ("content type",),
        "Link": ("post link",),
    }.items():
        c = find_col(df, *needles)
        if c:
            ren[c] = want
    df = df.rename(columns=ren)
    if "Created" in df.columns:
        df["Created"] = pd.to_datetime(df["Created"], errors="coerce", dayfirst=False)
    if "ContentType" in df.columns:
        df["ContentType"] = df["ContentType"].fillna("Image / Text").replace("", "Image / Text")
    else:
        df["ContentType"] = "Image / Text"
    return df


def top_posts(res, by: str = "EngRate", n: int = 5) -> Optional[pd.DataFrame]:
    df = _post_frame(res)
    if df is None or by not in df.columns:
        return None
    cols = [c for c in ["Title", "ContentType", "Created", "Impressions", "EngRate",
                        "Likes", "Comments", "Reposts", "Clicks", "Link"] if c in df.columns]
    return df.sort_values(by, ascending=False).head(n)[cols].reset_index(drop=True)


def content_type_perf(res) -> Optional[pd.DataFrame]:
    df = _post_frame(res)
    if df is None or "ContentType" not in df.columns:
        return None
    agg = {}
    if "Impressions" in df.columns:
        agg["Impressions"] = "mean"
    if "EngRate" in df.columns:
        agg["EngRate"] = "mean"
    if not agg:
        return None
    out = df.groupby("ContentType").agg(agg)
    out["Posts"] = df.groupby("ContentType").size()
    return out.reset_index().sort_values("EngRate" if "EngRate" in out else "Impressions",
                                         ascending=False)


def cadence(res) -> Optional[dict]:
    """Posting cadence vs engagement, by weekday. Small samples are flagged in UI."""
    df = _post_frame(res)
    if df is None or "Created" not in df.columns or df["Created"].isna().all():
        return None
    d = df.dropna(subset=["Created"]).copy()
    d["Weekday"] = d["Created"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    counts = d.groupby("Weekday").size().reindex(order).fillna(0)
    er = (d.groupby("Weekday")["EngRate"].mean().reindex(order)
          if "EngRate" in d.columns else pd.Series(index=order, dtype=float))
    span_days = (d["Created"].max() - d["Created"].min()).days + 1
    return {
        "n_posts": len(d),
        "span_days": span_days,
        "per_week": round(len(d) / max(span_days / 7, 1e-9), 1),
        "by_weekday": pd.DataFrame({"Weekday": order, "Posts": counts.values,
                                    "Avg engagement rate": er.values}),
    }


# --------------------------------------------------------------------------- #
# Visitors (LinkedIn page visitors)
# --------------------------------------------------------------------------- #
def visitors_summary(res, prev_res=None) -> Optional[dict]:
    ts = res.time_series
    if ts is None or "Date" not in ts.columns:
        return None
    # NB: the base label already contains "Total", so match the parenthetical
    # suffix "(total)"/"(desktop)"/"(mobile)" to disambiguate the sub-columns.
    pv_c = find_col(ts, "total page views", "(total)")
    uv_c = find_col(ts, "total unique visitors", "(total)")
    pv_desk = find_col(ts, "total page views", "(desktop)")
    pv_mob = find_col(ts, "total page views", "(mobile)")

    # section split (Overview / Life / Jobs) using each section's total page views
    sections = {}
    for sec in ["Overview", "Life", "Jobs"]:
        c = find_col(ts, sec.lower(), "page views", "(total)")
        if c:
            sections[sec] = int(pd.to_numeric(ts[c], errors="coerce").sum())

    daily = ts.copy()
    total_pv = int(daily[pv_c].sum()) if pv_c else None

    pop_pv_delta = None
    if prev_res is not None and total_pv is not None:
        pv = visitors_summary(prev_res)
        if pv and pv["total_page_views"]:
            pop_pv_delta = pct_delta(total_pv, pv["total_page_views"])

    return {
        "daily": daily,
        "pv_col": pv_c,
        "uv_col": uv_c,
        "total_page_views": total_pv,
        "total_unique": int(daily[uv_c].sum()) if uv_c else None,
        "device_split": {
            "Desktop": int(daily[pv_desk].sum()) if pv_desk else None,
            "Mobile": int(daily[pv_mob].sum()) if pv_mob else None,
        },
        "section_split": sections,
        "pop_pv_delta": pop_pv_delta,
        "split_pv": split_half(daily.set_index("Date")[pv_c]) if pv_c else {"available": False},
    }


# --------------------------------------------------------------------------- #
# Demographics (shared shape: label column + value column)
# --------------------------------------------------------------------------- #
def demographic_table(res, name: str, top: int = 10) -> Optional[pd.DataFrame]:
    d = res.demographics.get(name)
    if d is None or d.empty:
        return None
    label_c, val_c = d.columns[0], d.columns[-1]
    out = d[[label_c, val_c]].copy()
    out[val_c] = pd.to_numeric(out[val_c], errors="coerce")
    out = out.dropna(subset=[val_c]).sort_values(val_c, ascending=False)
    total = out[val_c].sum()
    out["share"] = out[val_c] / total if total else 0
    return out.head(top).reset_index(drop=True)
