"""
Deterministic findings engine.

Turns computed metrics into (1) headline KPIs spanning both channels and
(2) prioritized plain-English takeaways. This is the single source of truth for
the executive summary and — in Milestone 5 — the recommendations and the
optional AI narrative (which may only rephrase these verified statements).
"""
from __future__ import annotations

import pandas as pd

import ui
from analysis import linkedin as L
from analysis import ga4 as G
from analysis import cross_channel as CC

# LinkedIn engagement-rate benchmark (public rule-of-thumb band)
_LI_ER_BENCH = (0.02, 0.04)


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


# --------------------------------------------------------------------------- #
def _delta_ctx(pop, split):
    """(delta, context) — prefer true period-over-period, else within-window split."""
    if pop is not None:
        return pop, "vs previous period"
    if split.get("available"):
        return split.get("delta"), "recent vs prior half"
    return None, ""


def headline_kpis(data: dict, ga4=None, prev_data: dict | None = None) -> list[dict]:
    """Cross-channel headline KPI cards for the executive summary."""
    cards = []
    prev_data = prev_data or {}
    followers = data.get("followers")
    content = data.get("content")

    if followers:
        f = L.followers_summary(followers, prev_res=prev_data.get("followers"))
        if f:
            d, ctx = _delta_ctx(f["pop_new_delta"], f["split"])
            cards.append({"group": "LinkedIn", "label": "New followers",
                          "value": ui.fmt_int(f["new_total"]), "delta": d, "context": ctx,
                          "hint": "People who newly followed the CyberproAI LinkedIn page this period."})
    if content:
        c = L.content_summary(content, prev_res=prev_data.get("content"))
        if c:
            d, ctx = _delta_ctx(c["pop_impressions_delta"], c["split_impressions"])
            cards.append({"group": "LinkedIn", "label": "Post impressions",
                          "value": ui.fmt_int(c["total_impressions"]), "delta": d, "context": ctx,
                          "hint": "Times our LinkedIn posts were shown in feeds this period."})
            cards.append({"group": "LinkedIn", "label": "Engagement rate",
                          "value": _pct(c["agg_engagement_rate"]), "delta": None, "context": "",
                          "hint": "Share of post impressions that led to a click, reaction, comment or repost."})
    if ga4 is not None and (ga4.timeseries is not None or ga4.totals):
        s = G.summarize(ga4)["kpis"]
        _ga4_hints = {
            "totalUsers": "People who visited the CyberproAI website.",
            "sessions": "Visits to the website (one person can have several).",
            "keyEvents": "Conversions / important actions on the site (e.g. form fills).",
        }
        for m in ("totalUsers", "sessions", "keyEvents"):
            if m in s:
                k = s[m]
                val = (G.fmt_duration(k["value"]) if m == "averageSessionDuration"
                       else ui.fmt_pct(k["value"]) if m == "engagementRate"
                       else ui.fmt_int(k["value"]))
                cards.append({"group": "Website", "label": k["label"], "value": val,
                              "delta": k["delta"], "context": k["context"],
                              "hint": _ga4_hints.get(m, "")})
    return cards


# --------------------------------------------------------------------------- #
def takeaways(data: dict, ga4=None, merged: pd.DataFrame | None = None,
              corrs: list[dict] | None = None, top: int = 5,
              prev_data: dict | None = None) -> list[dict]:
    """Prioritized list of {text, tone, priority}. Highest priority first."""
    cand: list[dict] = []
    prev_data = prev_data or {}
    followers = data.get("followers")
    content = data.get("content")

    # --- Followers ---
    if followers:
        f = L.followers_summary(followers, prev_res=prev_data.get("followers"))
        if f:
            # Prefer true period-over-period; fall back to the within-window split.
            pop = f["pop_new_delta"]
            d = pop if pop is not None else (f["split"].get("delta") if f["split"].get("available") else None)
            basis = "vs the previous period" if pop is not None else "in the recent half vs the prior half"
            if d is not None and d >= 0.15:
                cand.append({"text": f"**Follower acquisition is accelerating** — {f['new_total']:,} "
                             f"new followers this period, up {d:.0%} {basis}.",
                             "tone": "good", "priority": 80 + min(abs(d) * 40, 40)})
            elif d is not None and d <= -0.15:
                cand.append({"text": f"**Follower growth is cooling** — {f['new_total']:,} new followers, "
                             f"down {abs(d):.0%} {basis}.",
                             "tone": "bad", "priority": 80 + min(abs(d) * 40, 40)})
            if f.get("sponsored") in (0, None) and f["new_total"] > 0:
                cand.append({"text": "**All follower growth was organic** — no paid follower spend detected. "
                             "Efficient, but paid amplification is an untapped lever.",
                             "tone": "neutral", "priority": 55})

    # --- Content ---
    if content:
        c = L.content_summary(content, prev_res=prev_data.get("content"))
        if c:
            pop_i = c["pop_impressions_delta"]
            si = c["split_impressions"]
            di = pop_i if pop_i is not None else (si.get("delta") if si.get("available") else None)
            basis_i = "vs the previous period" if pop_i is not None else "in the recent half"
            if di is not None and abs(di) >= 0.2:
                up = di > 0
                cand.append({"text": f"**Content reach {'rose' if up else 'fell'} {abs(di):.0%}** "
                             f"{basis_i} ({c['total_impressions']:,} impressions total).",
                             "tone": "good" if up else "bad", "priority": 70 + min(abs(di) * 30, 30)})
            er = c["agg_engagement_rate"]
            if er is not None:
                if er >= _LI_ER_BENCH[1]:
                    cand.append({"text": f"**Engagement rate is strong at {er:.1%}** — above the typical "
                                 f"{_LI_ER_BENCH[0]:.0%}–{_LI_ER_BENCH[1]:.0%} LinkedIn band.",
                                 "tone": "good", "priority": 62})
                elif er < _LI_ER_BENCH[0]:
                    cand.append({"text": f"**Engagement rate is {er:.1%}**, below the typical "
                                 f"{_LI_ER_BENCH[0]:.0%}–{_LI_ER_BENCH[1]:.0%} band — content resonance needs work.",
                                 "tone": "bad", "priority": 62})
        perf = L.content_type_perf(content)
        if perf is not None and "EngRate" in perf and len(perf) >= 2:
            best = perf.iloc[0]
            rest = perf.iloc[1:]["EngRate"].mean()
            if rest and best["EngRate"] >= rest * 1.25:
                mult = best["EngRate"] / rest if rest else 0
                cand.append({"text": f"**{best['ContentType']} posts engage ~{mult:.1f}× the rest** "
                             f"({best['EngRate']:.1%} vs {rest:.1%}) — a clear format to lean into.",
                             "tone": "good", "priority": 68})
        cad = L.cadence(content)
        if cad:
            wd = cad["by_weekday"].dropna(subset=["Avg engagement rate"])
            if len(wd) >= 2:
                bestrow = wd.loc[wd["Avg engagement rate"].idxmax()]
                cand.append({"text": f"**{bestrow['Weekday']} posts engage best** on average "
                             f"({bestrow['Avg engagement rate']:.1%}); cadence is ~{cad['per_week']}/week.",
                             "tone": "neutral", "priority": 48})

    # --- GA4 ---
    if ga4 is not None and (ga4.by_channel is not None or ga4.totals):
        if ga4.by_channel is not None and "sessions" in ga4.by_channel.columns and not ga4.by_channel.empty:
            ch = ga4.by_channel.copy()
            ch["sessions"] = pd.to_numeric(ch["sessions"], errors="coerce")
            ch = ch.sort_values("sessions", ascending=False)
            total = ch["sessions"].sum()
            topch = ch.iloc[0]
            share = topch["sessions"] / total if total else 0
            cand.append({"text": f"**{topch.iloc[0]} drives the most website sessions** "
                         f"({share:.0%} of traffic).", "tone": "neutral", "priority": 58})
        s = G.summarize(ga4)["kpis"]
        if "totalUsers" in s and s["totalUsers"]["delta"] is not None:
            d = s["totalUsers"]["delta"]
            if abs(d) >= 0.15:
                cand.append({"text": f"**Website users {'grew' if d>0 else 'declined'} {abs(d):.0%}** "
                             f"{s['totalUsers']['context']}.", "tone": "good" if d > 0 else "bad",
                             "priority": 66 + min(abs(d) * 20, 20)})

    # --- Cross-channel ---
    if corrs:
        best = corrs[0]
        if abs(best["r"]) >= 0.4:
            dircn = "directional (small sample)" if best["directional"] else f"n={best['n']} days"
            cand.append({"text": f"**{best['x_label']} tracks with {best['y_label']}** "
                         f"(r={best['r']:.2f}, {dircn}) — LinkedIn activity appears to move "
                         f"{best['y_label'].lower()}.", "tone": "good", "priority": 75})
    if merged is not None and not merged.empty:
        for tgt in ("social_sessions", "li_page_views"):
            lift = CC.post_day_lift(merged, tgt)
            if lift and lift["lift"] is not None and abs(lift["lift"]) >= 0.15:
                cand.append({"text": f"**On days we post, {CC.COL_LABELS[tgt].lower()} run "
                             f"{lift['lift']:+.0%}** vs non-posting days "
                             f"({lift['post_avg']:.0f} vs {lift['nonpost_avg']:.0f}).",
                             "tone": "good" if lift["lift"] > 0 else "bad", "priority": 72})
                break

    cand.sort(key=lambda x: x["priority"], reverse=True)
    # de-dupe by text, keep order
    seen, out = set(), []
    for c in cand:
        if c["text"] in seen:
            continue
        seen.add(c["text"])
        out.append(c)
    return out[:top]
