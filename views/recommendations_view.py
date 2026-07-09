"""Recommendations & major learnings — written analysis + prioritized actions."""
from __future__ import annotations

import streamlit as st

import branding as B
import ui
from analysis import cross_channel as CC
from analysis import findings as F
from narrative import engine as N

_PRIO_COLOR = {"High": B.BAD, "Medium": B.WARN, "Low": B.MUTED}
_PRIO_ORDER = ["High", "Medium", "Low"]


def _rec_card(r: dict):
    color = _PRIO_COLOR.get(r["priority"], B.CYAN)
    st.markdown(
        f"""<div style="border:1px solid {B.BORDER}; border-left:4px solid {color};
             background:{B.SURFACE}; padding:12px 16px; margin:8px 0; border-radius:0 8px 8px 0;
             box-shadow:0 1px 3px rgba(11,18,32,0.05);">
          <div style="display:flex; gap:8px; align-items:center; margin-bottom:4px;">
            <span class="cpai-pill" style="background:{color}22; color:{color};">{r['priority']}</span>
            <span style="color:{B.MUTED}; font-size:0.75rem; text-transform:uppercase;
                  letter-spacing:0.05em;">{r['category']}</span>
          </div>
          <div style="font-weight:700; color:{B.INK}; margin-bottom:2px;">{r['title']}</div>
          <div style="color:{B.MUTED}; font-size:0.9rem;">{r['detail']}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render(data: dict, ga4=None):
    ui.section_header("Recommendations & major learnings",
                      "What the numbers say to do next — prioritized for leadership.")

    has_li = any(data.get(k) for k in ("followers", "content", "visitors"))
    has_ga4 = ga4 is not None and (ga4.timeseries is not None or bool(ga4.totals))
    if not has_li and not has_ga4:
        st.info("Load LinkedIn exports and/or connect GA4 to generate recommendations.")
        return

    merged = CC.build_daily(data, ga4) if has_li else None
    corrs = CC.correlations(merged) if merged is not None and not merged.empty else []
    kpis = F.headline_kpis(data, ga4)
    tks = F.takeaways(data, ga4, merged, corrs)
    recs = N.recommendations(data, ga4, merged, corrs)

    # ---- Written analysis ----
    st.markdown("### Executive analysis")
    ai = N.ai_status()
    c1, c2 = st.columns([4, 1])
    if ai["available"]:
        c1.markdown(f'<span class="cpai-pill ok">✦ AI-written</span> '
                    f'<span style="color:{B.MUTED};font-size:0.8rem;">model: {ai["model"]}</span>',
                    unsafe_allow_html=True)
        regen = c2.button("↻ Regenerate", use_container_width=True)
        if regen or "rec_narrative" not in st.session_state:
            with st.spinner("Writing analysis with Claude…"):
                st.session_state["rec_narrative"] = N.write_analysis(kpis, tks, recs)
        narr = st.session_state["rec_narrative"]
    else:
        c1.markdown('<span class="cpai-pill off">✎ Rule-based</span> '
                    f'<span style="color:{B.MUTED};font-size:0.8rem;">'
                    'add ANTHROPIC_API_KEY to .env for AI-written prose</span>',
                    unsafe_allow_html=True)
        narr = N.write_analysis(kpis, tks, recs, prefer_ai=False)

    if narr.get("error"):
        st.warning(narr["error"])
    st.markdown(narr["text"])
    st.caption("The analysis only describes the verified figures below — no numbers are invented.")

    # ---- The numbers behind it ----
    with st.expander("Numbers behind the analysis"):
        cols = st.columns(min(len(kpis), 4) or 1)
        for i, k in enumerate(kpis):
            ui.kpi(cols[i % len(cols)], k["label"], k["value"], k.get("delta"), k.get("context", ""))
        for t in tks:
            ui.takeaway(t["text"], t["tone"])

    # ---- Recommendations ----
    st.markdown("### Prioritized recommendations")
    if not recs:
        st.caption("No confident recommendations yet — load more data.")
        return
    st.caption("Priority is **relative** — it ranks this period's actions by likely impact so "
               "you know what to tackle first. **High** = do these now; **Low** = worthwhile but "
               "less urgent.")
    for tier in _PRIO_ORDER:
        group = [r for r in recs if r["priority"] == tier]
        if not group:
            continue
        st.markdown(f"**{tier} priority**")
        for r in group:
            _rec_card(r)
