"""Executive summary — the 3–5 things leadership should know, up top."""
from __future__ import annotations

import streamlit as st

import ui
from analysis import cross_channel as CC
from analysis import findings as F


def render(data: dict, ga4=None, prev_data: dict | None = None):
    ui.section_header("Executive summary",
                      "The most important takeaways this period, in plain business language.")

    has_li = any(data.get(k) for k in ("followers", "content", "visitors"))
    has_ga4 = ga4 is not None and (ga4.timeseries is not None or bool(ga4.totals))
    if not has_li and not has_ga4:
        st.info("Load LinkedIn exports and/or connect GA4 to generate the summary.")
        return

    # Headline KPIs — grouped by source so it's always clear what's LinkedIn vs website
    cards = F.headline_kpis(data, ga4, prev_data)
    groups = [("LinkedIn", "📣 LinkedIn (our company page)"),
              ("Website", "🌐 Website (Google Analytics)")]
    for key, heading in groups:
        gcards = [c for c in cards if c.get("group") == key]
        if not gcards:
            continue
        st.markdown(f"#### {heading}")
        for i in range(0, len(gcards), 4):
            row = gcards[i:i + 4]
            cols = st.columns(len(row))
            for col, c in zip(cols, row):
                ui.kpi(col, c["label"], c["value"], c.get("delta"), c.get("context", ""),
                       hint=c.get("hint", ""))

    # Key takeaways
    merged = CC.build_daily(data, ga4) if has_li else None
    corrs = CC.correlations(merged) if merged is not None and not merged.empty else []
    tks = F.takeaways(data, ga4, merged, corrs, prev_data=prev_data)

    st.markdown("### Key takeaways")
    if not tks:
        st.caption("Not enough data yet to surface confident takeaways.")
    for t in tks:
        ui.takeaway(t["text"], t["tone"])

    # Coverage note
    loaded = [lbl for k, lbl in (("followers", "Followers"), ("content", "Content"),
                                 ("visitors", "Page visitors")) if data.get(k)]
    src = ", ".join(loaded) if loaded else "none"
    web = "connected" if has_ga4 else "not connected"
    ui.note(f"Coverage — LinkedIn: {src}. Website (GA4): {web}. "
            "Deltas compare the recent half of the window to the prior half unless a live "
            "GA4 previous-period comparison is available.")
