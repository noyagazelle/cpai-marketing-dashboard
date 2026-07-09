"""LinkedIn deep-dive view — renders followers, content, and page-visitor analysis."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import config
import glossary as GL
import ui
from analysis import linkedin as L

_DEMO_TITLES = {
    "Seniority": "By seniority",
    "Job function": "By job function",
    "Industry": "By industry",
    "Company size": "By company size",
    "Location": "By location",
}

# Explains the ▲/▼ on LinkedIn KPIs. Two cases: a previous saved period exists
# (true period-over-period) or not (within-window split-half).
_DELTA_NOTE_SPLIT = (
    "▲/▼ shows **momentum within this period** — its second half vs its first half. "
    "There's no earlier saved period yet, so upload next period's files and this becomes a "
    "true period-over-period comparison.")
_DELTA_NOTE_POP = (
    "▲/▼ compares this period against your **previous saved period** (true period-over-period).")


def _delta(pop, split):
    """Prefer a true period-over-period delta; fall back to the within-window split."""
    if pop is not None:
        return pop, "vs previous period"
    return _split_context(split)


def _split_context(split: dict) -> tuple:
    """(delta, label) for a split-half comparison, or (None, '') if unavailable."""
    if not split or not split.get("available"):
        return None, ""
    d = split["half_days"]
    return split["delta"], f"last {d}d vs prior {d}d"


def _demographics_block(res, title: str):
    if not res.demographics:
        return
    st.markdown(f"#### {title}")
    names = list(res.demographics.keys())
    tabs = st.tabs([_DEMO_TITLES.get(n, n) for n in names])
    for tab, name in zip(tabs, names):
        with tab:
            df = L.demographic_table(res, name, top=10)
            if df is None or df.empty:
                st.caption("No data.")
                continue
            label_c, val_c = df.columns[0], df.columns[1]
            fig = charts.hbars(df[label_c][::-1], df[val_c][::-1], percent=False)
            st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
def render(data: dict, prev_data: dict | None = None):
    followers = data.get("followers")
    content = data.get("content")
    visitors = data.get("visitors")
    prev_data = prev_data or {}
    prev_followers = prev_data.get("followers")
    prev_content = prev_data.get("content")
    prev_visitors = prev_data.get("visitors")

    if not any([followers, content, visitors]):
        st.info("No LinkedIn exports loaded. Add Followers, Content, or Visitors files on the left.")
        return

    # ===================================================================== #
    # FOLLOWERS
    # ===================================================================== #
    if followers:
        known_total = st.session_state.get("total_followers") or config.follower_base()
        f = L.followers_summary(followers, known_total=known_total, prev_res=prev_followers)
        ui.section_header("Follower growth", "New followers gained during the loaded window.")
        if f:
            delta, ctx = _delta(f["pop_new_delta"], f["split"])
            c1, c2, c3, c4 = st.columns(4)
            ui.kpi(c1, "New followers (period)", ui.fmt_int(f["new_total"]), delta, ctx,
                   hint=GL.hint("new_followers"))
            ui.kpi(c2, "Avg / day", ui.fmt_int(f["avg_daily"]), hint=GL.hint("avg_followers_day"))
            if f["audience_is_known"]:
                ui.kpi(c3, "Total followers", ui.fmt_int(f["audience_estimate"]),
                       context="from LinkedIn", hint=GL.hint("total_followers"))
            else:
                ui.kpi(c3, "Est. audience", ui.fmt_int(f["audience_estimate"]),
                       context="≈ from demographics", hint=GL.hint("est_audience"))
            ui.kpi(c4, "Period growth", ui.fmt_pct(f["growth_rate"]) if f["growth_rate"] else "—",
                   context="of total followers", hint=GL.hint("period_growth"))
            st.caption(_DELTA_NOTE_POP if f["pop_new_delta"] is not None else _DELTA_NOTE_SPLIT)

            left, right = st.columns([3, 2])
            with left:
                st.plotly_chart(
                    charts.line(f["daily"], "Date", "Cumulative (period)",
                                title="Cumulative new followers", fill=True),
                    use_container_width=True)
                st.plotly_chart(
                    charts.bars(f["daily"], "Date", "New followers",
                                title="New followers per day"),
                    use_container_width=True)
            with right:
                # organic vs sponsored vs auto-invited
                mix = {k.replace("_", " ").title(): f[k]
                       for k in ("organic", "sponsored", "auto_invited")
                       if f.get(k) is not None and f[k] > 0}
                if mix:
                    st.plotly_chart(
                        charts.donut(list(mix.keys()), list(mix.values()),
                                     title="Acquisition mix"),
                        use_container_width=True)
                    st.caption("How new followers were gained: **Organic** (found you naturally), "
                               "**Sponsored** (from paid ad campaigns), or **Auto-invited**. "
                               "100% organic means no paid follower campaigns ran this period.")
                bd = f["best_day"]
                ui.note(f"Best day: **{bd[0]:%b %d}** with **{bd[1]}** new followers.", "ok")
                if f["sponsored"] in (0, None):
                    ui.note("All growth was **organic** this period — no paid follower spend detected.")

            _demographics_block(followers, "Who follows CyberproAI")
        st.divider()

    # ===================================================================== #
    # CONTENT
    # ===================================================================== #
    if content:
        c = L.content_summary(content, prev_res=prev_content)
        ui.section_header("Content performance", "Impressions, engagement, and top posts.")
        if c:
            d_imp, ctx_i = _delta(c["pop_impressions_delta"], c["split_impressions"])
            d_eng, ctx_e = _delta(c["pop_engagements_delta"], c["split_engagements"])
            k1, k2, k3, k4 = st.columns(4)
            ui.kpi(k1, "Impressions", ui.fmt_int(c["total_impressions"]), d_imp, ctx_i,
                   hint=GL.hint("impressions"))
            ui.kpi(k2, "Engagements", ui.fmt_int(c["total_engagements"]), d_eng, ctx_e,
                   hint=GL.hint("engagements"))
            ui.kpi(k3, "Engagement rate", ui.fmt_pct(c["agg_engagement_rate"]),
                   context="eng ÷ impressions", hint=GL.hint("engagement_rate"))
            ui.kpi(k4, "Reactions / Comments / Reposts",
                   f'{ui.fmt_int(c["total_reactions"])} / {ui.fmt_int(c["total_comments"])} / {ui.fmt_int(c["total_reposts"])}',
                   hint=GL.hint("reactions_comments_reposts"))
            st.caption(_DELTA_NOTE_POP if c["pop_impressions_delta"] is not None else _DELTA_NOTE_SPLIT)

            cc1, cc2 = st.columns(2)
            if c["impressions_col"]:
                cc1.plotly_chart(
                    charts.line(c["daily"], "Date", c["impressions_col"],
                                title="Daily impressions", fill=True),
                    use_container_width=True)
            if c["er_col"]:
                fig = charts.line(c["daily"], "Date", c["er_col"], title="Daily engagement rate")
                fig.update_yaxes(tickformat=".0%")
                cc2.plotly_chart(fig, use_container_width=True)

            # Top posts
            st.markdown("#### Top posts")
            metric = st.radio("Rank by", ["Engagement rate", "Impressions"],
                              horizontal=True, key="li_topby")
            by = "EngRate" if metric == "Engagement rate" else "Impressions"
            tp = L.top_posts(content, by=by, n=5)
            if tp is not None and not tp.empty:
                show = tp.copy()
                if "Title" in show:
                    show["Title"] = show["Title"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 90) + "…"
                if "EngRate" in show:
                    show["EngRate"] = (show["EngRate"] * 100).round(2).astype(str) + "%"
                if "Created" in show:
                    show["Created"] = pd.to_datetime(show["Created"]).dt.strftime("%b %d")
                st.dataframe(
                    show, use_container_width=True, hide_index=True,
                    column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")}
                    if "Link" in show else None,
                )

            # Content type + cadence
            ct1, ct2 = st.columns(2)
            perf = L.content_type_perf(content)
            if perf is not None and not perf.empty and "EngRate" in perf:
                fig = charts.bars(perf, "ContentType", "EngRate",
                                  title="Avg engagement rate by content type", percent=True)
                ct1.plotly_chart(fig, use_container_width=True)
            cad = L.cadence(content)
            if cad:
                wd = cad["by_weekday"].dropna(subset=["Avg engagement rate"])
                if not wd.empty:
                    fig = charts.bars(wd, "Weekday", "Avg engagement rate",
                                      title="Avg engagement rate by weekday", percent=True,
                                      color=charts.B.TEAL)
                    ct2.plotly_chart(fig, use_container_width=True)
                ct2.caption(
                    f"Cadence: **{cad['n_posts']} posts** over {cad['span_days']} days "
                    f"(~{cad['per_week']}/week). Small sample — read weekday patterns as directional.")
        st.divider()

    # ===================================================================== #
    # PAGE VISITORS
    # ===================================================================== #
    if visitors:
        v = L.visitors_summary(visitors, prev_res=prev_visitors)
        ui.section_header("LinkedIn page visitors", "Traffic to the CyberproAI LinkedIn page itself.")
        if v:
            d_pv, ctx_pv = _delta(v["pop_pv_delta"], v["split_pv"])
            v1, v2, v3, v4 = st.columns(4)
            ui.kpi(v1, "Page views", ui.fmt_int(v["total_page_views"]), d_pv, ctx_pv,
                   hint=GL.hint("page_views"))
            ui.kpi(v2, "Unique visitors", ui.fmt_int(v["total_unique"]),
                   hint=GL.hint("unique_visitors"))
            dev = v["device_split"]
            tot_dev = (dev.get("Desktop") or 0) + (dev.get("Mobile") or 0)
            mob_share = (dev.get("Mobile") or 0) / tot_dev if tot_dev else None
            ui.kpi(v3, "Mobile share", ui.fmt_pct(mob_share) if mob_share is not None else "—",
                   hint=GL.hint("mobile_share"))
            top_sec = max(v["section_split"], key=v["section_split"].get) if v["section_split"] else "—"
            ui.kpi(v4, "Top page section", top_sec, hint=GL.hint("top_section"))

            vc1, vc2 = st.columns(2)
            if v["pv_col"]:
                fig = charts.line(v["daily"], "Date", [c for c in [v["pv_col"], v["uv_col"]] if c],
                                  title="Daily page views vs unique visitors",
                                  labels={v["pv_col"]: "Page views", v["uv_col"]: "Unique visitors"})
                vc1.plotly_chart(fig, use_container_width=True)
            if v["section_split"]:
                secs = {k: val for k, val in v["section_split"].items() if val}
                if secs:
                    vc2.plotly_chart(
                        charts.donut(list(secs.keys()), list(secs.values()),
                                     title="Page views by section"),
                        use_container_width=True)
            _demographics_block(visitors, "Who visits the page")
