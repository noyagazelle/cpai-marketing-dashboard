"""Website (GA4) deep-dive view — live API connection + CSV/Excel fallback."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import config
import glossary as GL
import loaders
import ui
from analysis import ga4 as A
from connectors import ga4 as GA4

_PCT = {"engagementRate"}
_DUR = {"averageSessionDuration"}


def _fmt_kpi(metric: str, value) -> str:
    if value is None:
        return "—"
    if metric in _PCT:
        return ui.fmt_pct(value)
    if metric in _DUR:
        return A.fmt_duration(value)
    return ui.fmt_int(value)


@st.cache_data(show_spinner="Querying GA4…", ttl=3600)
def _cached_fetch(start, end, prev_start, prev_end, _nonce):
    return GA4.fetch(start, end, prev_start, prev_end)


def _render_report(data):
    summary = A.summarize(data)
    kpis = summary["kpis"]
    order = [m for m in summary["order"] if m in kpis]

    # KPI cards (up to 4 per row)
    for i in range(0, len(order), 4):
        row = order[i:i + 4]
        cols = st.columns(len(row))
        for col, m in zip(cols, row):
            k = kpis[m]
            ui.kpi(col, k["label"], _fmt_kpi(m, k["value"]), k["delta"], k["context"],
                   hint=GL.ga4_hint(m))
    for n in summary["notes"]:
        ui.note(n, "warn" if "approximate" in n.lower() else "info")

    # Trends
    if data.timeseries is not None and not data.timeseries.empty:
        ts = data.timeseries
        c1, c2 = st.columns(2)
        ys = [m for m in ("totalUsers", "newUsers", "sessions") if m in ts.columns]
        if ys:
            c1.plotly_chart(
                charts.line(ts, "date", ys, title="Users & sessions over time",
                            labels={"totalUsers": "Users", "newUsers": "New users",
                                    "sessions": "Sessions"}),
                use_container_width=True)
        if "engagementRate" in ts.columns:
            fig = charts.line(ts, "date", "engagementRate", title="Engagement rate over time")
            fig.update_yaxes(tickformat=".0%")
            c2.plotly_chart(fig, use_container_width=True)

    # Channels + device
    c3, c4 = st.columns(2)
    ch = A.top_table(data.by_channel, "sessionDefaultChannelGroup", "sessions", 8)
    if ch is not None:
        dim = ch.columns[0]
        c3.plotly_chart(charts.hbars(ch[dim][::-1], ch["sessions"][::-1],
                                     title="Sessions by channel"), use_container_width=True)
    dev = data.by_device
    if dev is not None and not dev.empty and "sessions" in dev.columns:
        c4.plotly_chart(charts.donut(dev.iloc[:, 0], dev["sessions"],
                                     title="Sessions by device"), use_container_width=True)

    # Landing pages + top pages
    lp = A.top_table(data.landing_pages, "landingPage", "sessions", 10)
    if lp is not None:
        st.markdown("#### Top landing pages")
        st.dataframe(lp, use_container_width=True, hide_index=True)
    tp = A.top_table(data.top_pages, "pagePath", "screenPageViews", 10)
    if tp is not None:
        st.markdown("#### Top pages")
        st.dataframe(tp, use_container_width=True, hide_index=True)

    # Where visitors arrived from, per page
    ls = data.landing_sources
    if ls is not None and not ls.empty and "sessions" in ls.columns:
        st.markdown("#### Where visitors arrived from — by page")
        st.caption("Pick a page to see which channels sent people to it "
                   "(e.g. did the Bina webinar page get traffic from LinkedIn, search, or direct?).")
        ls = ls.copy()
        ls["sessions"] = pd.to_numeric(ls["sessions"], errors="coerce").fillna(0)
        pagecol, chcol = ls.columns[0], ls.columns[1]
        # rank pages by total sessions so the busiest are easy to find
        totals = ls.groupby(pagecol)["sessions"].sum().sort_values(ascending=False)
        pages = list(totals.index[:40])
        if pages:
            sel = st.selectbox("Page", pages, key="ga4_landing_pick",
                               format_func=lambda p: f"{p}  ({int(totals[p]):,} sessions)")
            sub = (ls[ls[pagecol] == sel][[chcol, "sessions"]]
                   .groupby(chcol, as_index=False)["sessions"].sum()
                   .sort_values("sessions", ascending=False))
            share = sub["sessions"].sum()
            top_ch = sub.iloc[0]
            st.markdown(f"**{sel}** — {int(share):,} sessions. Top source: "
                        f"**{top_ch[chcol]}** ({top_ch['sessions']/share:.0%} of its traffic).")
            st.plotly_chart(
                charts.hbars(sub[chcol][::-1], sub["sessions"][::-1],
                             title=f"How people reached {sel}"),
                use_container_width=True)

    # Geography
    country = A.top_table(data.by_country, "country", "totalUsers", 10)
    if country is not None:
        st.markdown("#### Top countries")
        st.plotly_chart(charts.hbars(country.iloc[:, 0][::-1], country["totalUsers"][::-1],
                                     title="Users by country"), use_container_width=True)


# --------------------------------------------------------------------------- #
def connect_panel():
    """Reusable GA4 connect/upload panel. Writes to st.session_state['ga4_data'].
    Used both here and in the Upload & connect hub."""
    stt = GA4.status()
    with st.container(border=True):
        if stt["configured"]:
            st.markdown(f'<span class="cpai-pill ok">✓ Connected</span> '
                        f'Property `{stt["property_id"]}`', unsafe_allow_html=True)

            # Default the date range to the loaded LinkedIn period so the two
            # sources line up. Keying on the period signature means a new upload
            # re-syncs the dates automatically; manual edits persist until then.
            li_period = loaders.linkedin_period(st.session_state.get("li_data", {}))
            if li_period:
                default_start, default_end = li_period
                sig = f"{default_start}_{default_end}"
                st.caption(f"📅 Matched to your LinkedIn period "
                           f"({default_start:%b %d} → {default_end:%b %d, %Y}). Adjust to override.")
            else:
                default_start, default_end = config.default_period()
                sig = "rolling"

            d1, d2, d3 = st.columns([2, 2, 1])
            start = d1.date_input("From", value=default_start, key=f"ga4_from_{sig}")
            end = d2.date_input("To", value=default_end, key=f"ga4_to_{sig}")
            d3.markdown("<br>", unsafe_allow_html=True)
            refresh = d3.button("🔄 Refresh", use_container_width=True)
            if refresh:
                st.session_state["ga4_nonce"] = st.session_state.get("ga4_nonce", 0) + 1
            if start and end and start <= end:
                prev_start, prev_end = config.previous_period(start, end)
                try:
                    st.session_state["ga4_data"] = _cached_fetch(
                        start, end, prev_start, prev_end, st.session_state.get("ga4_nonce", 0))
                except Exception as e:
                    st.error(f"GA4 query failed: {e}")
        else:
            st.markdown('<span class="cpai-pill warn">⚠ Not connected</span> '
                        f'{stt["reason"]}', unsafe_allow_html=True)
            st.caption("Add credentials to `.env` (see README → GA4 setup) for a live "
                       "connection, **or** upload a manual export below. Either works.")
            up = st.file_uploader("Upload a GA4 CSV / Excel export",
                                  type=["csv", "xlsx", "xls"], key="ga4_upload")
            if up is not None:
                from parsing.ga4_csv import parse_ga4_export
                try:
                    st.session_state["ga4_data"] = parse_ga4_export(up, source_name=up.name)
                    st.success(f"Parsed **{up.name}** (manual export).")
                except Exception as e:
                    st.error(f"Could not parse **{up.name}**: {e}")


def render():
    ui.section_header("Website analytics (GA4)",
                      "Live Google Analytics 4 data, or a manual CSV/Excel export.")
    connect_panel()

    data = st.session_state.get("ga4_data")
    if data is None:
        st.info("No website data yet. Connect GA4 or upload an export above "
                "(or on the **Upload & connect** tab).")
        return
    src = "live GA4 API" if data.source == "api" else "manual export"
    rng = f"{data.start:%b %d} → {data.end:%b %d, %Y}" if data.start and data.end else ""
    st.caption(f"Showing: {src} · {rng}")
    _render_report(data)
