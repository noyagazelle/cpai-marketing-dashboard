"""
CyberproAI — Marketing Analytics Dashboard
Streamlit entry point.

Data flow: LinkedIn exports are parsed on the "Upload & connect" tab and stored
in st.session_state so every view sees them regardless of the active tab. GA4
data lives in st.session_state['ga4_data']. On first load we seed the bundled
sample data so the dashboard isn't empty.
"""
import hmac
from pathlib import Path

import streamlit as st

import branding as B
import config
import history
import loaders
from connectors import ga4
from views import (upload_view, executive_view, linkedin_view, ga4_view,
                   cross_channel_view, audience_view, recommendations_view, appendix_view)

st.set_page_config(
    page_title=f"{B.COMPANY_NAME} — {B.DASHBOARD_TITLE}",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(B.CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Password gate — active only when APP_PASSWORD is set (i.e. when deployed).
# Runs server-side, so the password is never exposed to the browser.
# --------------------------------------------------------------------------- #
def _password_gate():
    pw = config.get("APP_PASSWORD")
    if not pw or st.session_state.get("_authed"):
        return
    st.markdown(f"## 🔒 {B.COMPANY_NAME} · Marketing Analytics")
    st.caption("This dashboard is private. Enter the team password to continue.")
    entered = st.text_input("Team password", type="password")
    if entered:
        if hmac.compare_digest(entered, str(pw)):
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password — try again.")
    st.stop()


_password_gate()

# On first load (or after a session/server reset), restore data durably:
#   1) the last uploaded working set (survives resets), else
#   2) the most recent saved period, else
#   3) bundled sample data.
if "li_data" not in st.session_state:
    _current = history.load_current()
    if _current:
        st.session_state["li_data"] = _current
        _p = loaders.linkedin_period(_current)
        st.session_state["li_source"] = (f"your uploaded files ({_p[0]:%b %d} → {_p[1]:%b %d, %Y})"
                                          if _p else "your uploaded files")
    else:
        _periods = history.list_periods()
        if _periods:
            _latest = _periods[-1]
            st.session_state["li_data"] = history.load_period(_latest["key"])
            st.session_state["li_source"] = f"saved period {_latest['start']} → {_latest['end']}"
        else:
            st.session_state["li_data"] = loaders.load_samples()
            st.session_state["li_source"] = "bundled sample data (June 2026)"


# --------------------------------------------------------------------------- #
# Sidebar — brand + at-a-glance status (loading happens on the Upload tab)
# --------------------------------------------------------------------------- #
with st.sidebar:
    if Path(B.LOGO_PATH).exists():
        st.image(B.LOGO_PATH, width=180)
    st.markdown(f"### {B.DASHBOARD_TITLE}")
    st.caption("Load or update each period's data on the **Upload & connect** tab.")
    st.divider()
    _d = st.session_state.get("li_data", {})
    st.markdown("**Loaded**")
    st.caption("LinkedIn: " + (", ".join(_d[k].label for k in _d) if _d else "none"))
    _stt = ga4.status()
    ga4_state = ("connected" if _stt["configured"]
                 else "manual upload" if st.session_state.get("ga4_data") else "not connected")
    st.caption(f"Website (GA4): {ga4_state}")


# --------------------------------------------------------------------------- #
# Header + top navigation
# --------------------------------------------------------------------------- #
st.title(f"{B.COMPANY_NAME} · Marketing Analytics")

page = st.radio(
    "Navigate",
    ["Upload & connect", "Executive summary", "LinkedIn deep dive", "Website (GA4)",
     "Cross-channel", "Audience", "Recommendations", "Data & export"],
    index=0, horizontal=True, label_visibility="collapsed",
)
st.divider()

data = st.session_state.get("li_data", {})
source_note = st.session_state.get("li_source")
_ga4_data = st.session_state.get("ga4_data")

# Previous LinkedIn period (for true period-over-period), if one is stored.
prev_data = {}
_prev_label = None
_cur_period = loaders.linkedin_period(data)
if _cur_period:
    _prev_key = history.previous_key(f"{_cur_period[0]:%Y-%m-%d}",
                                     override=st.session_state.get("compare_key"))
    if _prev_key:
        prev_data = history.load_period(_prev_key)
        _pp = loaders.linkedin_period(prev_data)
        _prev_label = (f"{_pp[0]:%b %d} → {_pp[1]:%b %d, %Y}" if _pp else _prev_key)

# Prominent period bar at the top of EVERY tab, so what you're looking at is always clear.
if data:
    _is_sample = str(source_note).lower().startswith(("bundled", "sample"))
    _view = (f"{_cur_period[0]:%b %d} → {_cur_period[1]:%b %d, %Y}" if _cur_period else str(source_note))
    _src_tag = "🧪 sample data" if _is_sample else "📊 your uploaded files"
    _cmp = _prev_label if _prev_label else "— no earlier period saved yet"
    if _ga4_data is not None and getattr(_ga4_data, "start", None) and getattr(_ga4_data, "end", None):
        _ga4_lbl = f"{_ga4_data.start:%b %d} → {_ga4_data.end:%b %d, %Y}"
    else:
        _ga4_lbl = "not connected"
    st.markdown(
        f"""<div style="background:{B.SURFACE}; border:1px solid {B.BORDER}; border-radius:10px;
             padding:10px 16px; margin-bottom:10px; font-size:0.9rem; color:{B.INK};">
          📅 <b>Viewing:</b> {_view} &nbsp;<span style="color:{B.MUTED};">({_src_tag})</span>
          &nbsp;&nbsp;·&nbsp;&nbsp; <b>Compared to:</b> {_cmp}
          &nbsp;&nbsp;·&nbsp;&nbsp; <b>Website (GA4):</b> {_ga4_lbl}
        </div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #
if page == "Upload & connect":
    upload_view.render()
elif page == "Executive summary":
    executive_view.render(data, _ga4_data, prev_data)
elif page == "LinkedIn deep dive":
    if not data:
        st.info("No LinkedIn data loaded. Add exports on the **Upload & connect** tab.")
    else:
        linkedin_view.render(data, prev_data)
elif page == "Website (GA4)":
    ga4_view.render()
elif page == "Cross-channel":
    cross_channel_view.render(data, _ga4_data)
elif page == "Audience":
    audience_view.render(data, _ga4_data)
elif page == "Recommendations":
    recommendations_view.render(data, _ga4_data)
elif page == "Data & export":
    appendix_view.render(data, _ga4_data, source_note)

st.divider()
st.caption(
    "CyberproAI · Marketing Analytics — LinkedIn + Google Analytics. "
    "All figures computed directly from your data; the written analysis only describes them."
)
