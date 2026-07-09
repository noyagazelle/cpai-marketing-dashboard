"""Cross-channel impact — does LinkedIn activity drive traffic and outcomes?"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import glossary as GL
import ui
from analysis import cross_channel as CC


def _corr_cards(corrs: list[dict], limit: int = 3):
    if not corrs:
        st.caption("Not enough overlapping daily data (need ≥7 days) to compute correlations.")
        return
    cols = st.columns(min(len(corrs), limit))
    for col, c in zip(cols, corrs[:limit]):
        tone = "good" if c["r"] > 0 else "bad"
        arrow = "▲" if c["r"] > 0 else "▼"
        note = "directional · small sample" if c["directional"] else f"n = {c['n']} days"
        col.markdown(
            f"""<div class="cpai-kpi">
                <div class="label">{c['x_label']} → {c['y_label']}</div>
                <div class="value">r = {c['r']:.2f}</div>
                <div class="{'delta-up' if c['r']>0 else 'delta-down'}">{arrow} {c['strength']} · {note}</div>
            </div>""", unsafe_allow_html=True)


def render(data: dict, ga4=None):
    ui.section_header("Cross-channel impact",
                      "Correlating LinkedIn activity with downstream traffic and outcomes.")

    has_ga4 = ga4 is not None and (ga4.timeseries is not None or bool(ga4.totals))
    merged = CC.build_daily(data, ga4)
    if merged.empty:
        st.info("Load LinkedIn content/visitors (and optionally connect GA4) to run this analysis.")
        return

    if not has_ga4:
        ui.note("GA4 isn't connected, so the **website** link (LinkedIn → site sessions & "
                "conversions) can't be measured yet. Showing the LinkedIn-internal link "
                "(content activity → LinkedIn page visits), which uses your exports alone.", "warn")

    corrs = CC.correlations(merged)

    # Trend overlay: pick a driver and an outcome that both exist
    driver = "li_impressions" if "li_impressions" in merged else None
    outcome = next((c for c in ("social_sessions", "li_page_views", "ga4_sessions")
                    if c in merged.columns), None)
    if driver and outcome:
        post_days = None
        if "li_posts" in merged.columns:
            post_days = merged.loc[merged["li_posts"] > 0, "date"].tolist()
        st.markdown("#### Activity vs outcome, day by day")
        st.plotly_chart(
            charts.dual_axis(merged, "date", driver, outcome,
                             y1_label=CC.COL_LABELS[driver], y2_label=CC.COL_LABELS[outcome],
                             title=f"{CC.COL_LABELS[driver]} vs {CC.COL_LABELS[outcome]}",
                             markers_x=post_days),
            use_container_width=True)
        st.caption(
            f"**How to read this:** the **blue line** ({CC.COL_LABELS[driver].lower()}, left axis) "
            f"is our LinkedIn activity each day; the **teal line** ({CC.COL_LABELS[outcome].lower()}, "
            "right axis) is the outcome each day. The two lines use **separate scales** so you can "
            "compare their *shape*, not their size. **Dotted vertical lines** mark days we published "
            "a post. If the teal line tends to rise on or just after the blue line's peaks (and the "
            "dotted lines), our LinkedIn activity is likely driving that outcome."
            + ("  \n_Note: social-referral sessions can be low day-to-day for a smaller site, so this "
               "line may sit near zero._" if outcome == "social_sessions" else ""))

    st.markdown("#### Strongest relationships")
    st.caption("**r** is the correlation: " + GL.hint("correlation"))
    _corr_cards(corrs)

    # Post-day lift
    st.markdown("#### Posting-day lift")
    lift_shown = False
    for tgt in ("social_sessions", "li_page_views"):
        lift = CC.post_day_lift(merged, tgt)
        if lift:
            lift_shown = True
            c1, c2, c3 = st.columns(3)
            ui.kpi(c1, f"{CC.COL_LABELS[tgt]} · post days", ui.fmt_int(lift["post_avg"]),
                   context=f"{lift['n_post']} days", hint=GL.hint("post_day_avg"))
            ui.kpi(c2, f"{CC.COL_LABELS[tgt]} · quiet days", ui.fmt_int(lift["nonpost_avg"]),
                   context=f"{lift['n_nonpost']} days", hint=GL.hint("quiet_day_avg"))
            ui.kpi(c3, "Lift on posting days", ui.fmt_pct(lift["lift"]) if lift["lift"] is not None else "—",
                   lift["lift"], "post vs quiet", hint=GL.hint("post_lift"))
            break
    if not lift_shown:
        st.caption("Need at least a couple of posting days and quiet days in the window to compare.")

    with st.expander("Aligned daily data"):
        st.dataframe(merged, use_container_width=True, hide_index=True)

    if corrs:
        top = corrs[0]
        cav = ("This is an association, not proof of causation" +
               (" — and the sample is small, so read it as directional." if top["directional"]
                else "."))
        ui.note(f"Interpretation: {top['x_label'].lower()} and {top['y_label'].lower()} move "
                f"{'together' if top['r']>0 else 'inversely'} (r={top['r']:.2f}). {cav}")
