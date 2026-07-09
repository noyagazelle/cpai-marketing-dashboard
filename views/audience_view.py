"""Audience insights — who follows us vs who visits, and where they diverge."""
from __future__ import annotations

import streamlit as st

import charts
import ui
from analysis import linkedin as L
from analysis import ga4 as G

_CATS = ["Seniority", "Job function", "Industry", "Company size", "Location"]


def _top_label(res, name):
    df = L.demographic_table(res, name, top=1)
    if df is None or df.empty:
        return None, None
    return df.iloc[0, 0], df.iloc[0]["share"]


def render(data: dict, ga4=None):
    ui.section_header("Audience insights",
                      "The LinkedIn audience that follows us vs the audience that visits — and the site audience.")

    followers = data.get("followers")
    visitors = data.get("visitors")
    has_ga4 = ga4 is not None and (ga4.by_country is not None or ga4.by_device is not None)

    if not (followers or visitors or has_ga4):
        st.info("Load Followers/Visitors exports or connect GA4 to see audience insights.")
        return

    # Divergence highlights (followers vs visitors, per category)
    if followers and visitors:
        st.markdown("#### Followers vs page visitors — who they are")
        st.caption("**Followers** = people who follow the CyberproAI LinkedIn page. "
                   "**Page visitors** = people who viewed the page (they may not follow). "
                   "For each attribute below, we show the largest group in each — and whether the "
                   "two audiences look the same or different.")
        notes = []
        for cat in _CATS:
            if cat in followers.demographics and cat in visitors.demographics:
                fl, fs = _top_label(followers, cat)
                vl, vs = _top_label(visitors, cat)
                if fl and vl:
                    same = str(fl).strip().lower() == str(vl).strip().lower()
                    tone = "good" if same else "neutral"
                    noun = cat.lower()
                    if same:
                        msg = (f"**{cat}** — Both audiences are mostly **{fl}** "
                               f"(followers {fs:.0%}, visitors {vs:.0%}). They line up. ✅")
                    else:
                        msg = (f"**{cat}** — Followers are mostly **{fl}** ({fs:.0%}), but page "
                               f"visitors are mostly **{vl}** ({vs:.0%}). Different {noun} profiles. ⚠️")
                    notes.append((msg, tone))
        if notes:
            for msg, tone in notes[:5]:
                ui.takeaway(msg, tone)
        else:
            st.caption("These files don't share enough demographic detail to compare.")

    # Side-by-side breakdowns
    st.markdown("#### Breakdowns")
    cats_present = [c for c in _CATS
                    if (followers and c in followers.demographics) or (visitors and c in visitors.demographics)]
    if cats_present:
        tabs = st.tabs(cats_present)
        for tab, cat in zip(tabs, cats_present):
            with tab:
                cols = st.columns(2)
                if followers and cat in followers.demographics:
                    df = L.demographic_table(followers, cat, top=8)
                    if df is not None:
                        cols[0].markdown("**Followers**")
                        cols[0].plotly_chart(
                            charts.hbars(df.iloc[:, 0][::-1], df.iloc[:, 1][::-1]),
                            use_container_width=True)
                if visitors and cat in visitors.demographics:
                    df = L.demographic_table(visitors, cat, top=8)
                    if df is not None:
                        cols[1].markdown("**Page visitors**")
                        cols[1].plotly_chart(
                            charts.hbars(df.iloc[:, 0][::-1], df.iloc[:, 1][::-1], color=charts.B.TEAL_2),
                            use_container_width=True)

    # Site audience from GA4
    if has_ga4:
        st.markdown("#### Website audience (GA4)")
        cols = st.columns(2)
        country = G.top_table(ga4.by_country, "country", "totalUsers", 8)
        if country is not None:
            cols[0].plotly_chart(
                charts.hbars(country.iloc[:, 0][::-1], country["totalUsers"][::-1],
                             title="Users by country"), use_container_width=True)
        if ga4.by_device is not None and not ga4.by_device.empty and "totalUsers" in ga4.by_device.columns:
            cols[1].plotly_chart(
                charts.donut(ga4.by_device.iloc[:, 0], ga4.by_device["totalUsers"],
                             title="Users by device"), use_container_width=True)
    elif followers or visitors:
        ui.note("Connect GA4 to add the website audience (geography, device) alongside the "
                "LinkedIn audience.")
