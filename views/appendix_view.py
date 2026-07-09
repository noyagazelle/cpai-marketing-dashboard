"""Data appendix & export — loaded-data status, filterable tables, CSV/Excel download."""
from __future__ import annotations

import streamlit as st

import ui
from analysis import cross_channel as CC
from analysis import tables as T
from parsing import KIND_LABELS


def _pill(present: bool, label: str) -> str:
    cls = "ok" if present else "off"
    return f'<span class="cpai-pill {cls}">{"✓" if present else "—"} {label}</span>'


def _status(data: dict, ga4, source_note: str | None):
    st.markdown("### Loaded data")
    if source_note:
        st.caption(f"LinkedIn source: {source_note}")
    st.markdown(
        " ".join(_pill(k in data, KIND_LABELS[k])
                 for k in ("followers", "visitors", "content", "competitors"))
        + " " + _pill(ga4 is not None and (ga4.timeseries is not None or bool(ga4.totals)), "Website (GA4)"),
        unsafe_allow_html=True,
    )
    if data:
        cols = st.columns(len(data))
        for col, (kind, res) in zip(cols, data.items()):
            with col:
                st.markdown(f"**{res.label}**")
                st.caption(f"`{res.source_name}`")
                dr = res.date_range
                if dr:
                    col.caption(f"📅 {dr[0]:%b %d} → {dr[1]:%b %d, %Y} ({(dr[1]-dr[0]).days + 1} days)")
                for w in res.warnings:
                    st.warning(w, icon="⚠️")


def render(data: dict, ga4=None, source_note: str | None = None):
    ui.section_header("Data appendix & export",
                      "The underlying numbers — browse, filter, and download.")

    if not data and ga4 is None:
        st.info("No data loaded. Add LinkedIn exports or connect GA4 to browse the tables.")
        return

    _status(data, ga4, source_note)

    merged = CC.build_daily(data, ga4) if data else None
    tbls = T.collect_tables(data, ga4, merged)
    if not tbls:
        st.caption("No tabular data available yet.")
        return

    st.divider()

    # Download everything as one workbook
    top1, top2 = st.columns([3, 1])
    top1.markdown("### Browse a table")
    top2.download_button(
        "⬇︎ All tables (Excel)", data=T.to_excel_bytes(tbls),
        file_name="cyberpro_marketing_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    name = st.selectbox("Table", list(tbls.keys()))
    df = tbls[name]

    # simple free-text filter across string columns
    q = st.text_input("Filter rows (matches any text column)", "")
    view = df
    if q:
        strcols = [c for c in df.columns if df[c].dtype == object]
        if strcols:
            mask = df[strcols].apply(lambda s: s.astype(str).str.contains(q, case=False, na=False)).any(axis=1)
            view = df[mask]

    st.caption(f"{len(view):,} of {len(df):,} rows")
    st.dataframe(view, use_container_width=True, hide_index=True)

    d1, d2 = st.columns(2)
    safe = name.replace(" ", "_").replace("—", "-").replace("/", "-")
    d1.download_button("⬇︎ This table (CSV)", data=T.to_csv_bytes(view),
                       file_name=f"{safe}.csv", mime="text/csv", use_container_width=True)
    d2.download_button("⬇︎ This table (Excel)", data=T.to_excel_bytes({name: view}),
                       file_name=f"{safe}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
