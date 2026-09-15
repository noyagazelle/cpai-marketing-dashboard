"""
CyberproAI — Marketing Analytics Dashboard
Streamlit entry point.

Data flow: LinkedIn exports are parsed on the "Upload & connect" tab and stored
in st.session_state so every view sees them regardless of the active tab. GA4
data lives in st.session_state['ga4_data']. On first load we seed the bundled
sample data so the dashboard isn't empty.
"""
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth

import branding as B
import config
import history
import loaders
from connectors import ga4
from views import (upload_view, executive_view, linkedin_view, ga4_view,
                   cross_channel_view, audience_view, recommendations_view, appendix_view,
                   admin_view)

st.set_page_config(
    page_title=f"{B.COMPANY_NAME} — {B.DASHBOARD_TITLE}",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(B.CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Per-user login — active once someone is registered or invited. Each teammate
# sets their OWN password by self-registering: an admin invites their email on
# the "Manage access" tab, then they set up their account here on first visit.
# Runs server-side via streamlit-authenticator.
# --------------------------------------------------------------------------- #
def _auth_gate():
    users = config.auth_users() or {"usernames": {}}
    pending = config.pre_authorized_emails()
    if not users["usernames"] and not pending:
        return None  # nothing configured yet — local dev, no login screen

    authenticator = stauth.Authenticate(users, cookie_name="cpai_marketing_auth",
                                         cookie_key=config.auth_cookie_key(),
                                         cookie_expiry_days=7)
    st.markdown(f"## 🔒 {B.COMPANY_NAME} · Marketing Analytics")
    try:
        authenticator.login()
    except stauth.LoginError:
        # A browser cookie references a user that no longer exists in AUTH_USERS
        # (e.g. auth state was reset by a redeploy) — clear it and show a fresh
        # login screen instead of crashing.
        authenticator.cookie_controller.delete_cookie()
        st.rerun()
    status = st.session_state.get("authentication_status")

    if status is not True:
        if status is False:
            st.error("Incorrect username or password.")
        else:
            st.caption("This dashboard is private. Log in, or set up your account below if "
                       "you've been invited.")
        if pending:
            with st.expander("New here? Set up your account"):
                try:
                    email, username, name = authenticator.register_user(
                        pre_authorized=pending, captcha=False,
                        fields={"Register": "Create account"},
                    )
                except stauth.RegisterError as e:
                    st.error(str(e))
                else:
                    if email:
                        config.set_auth_users(users)
                        config.set_pre_authorized_emails(pending)
                        st.success(f"Account created for {name} — log in above with your new password.")
        st.stop()
    return authenticator


authenticator = _auth_gate()

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
    if authenticator is not None:
        st.caption(f"Logged in as **{st.session_state.get('name')}**")
        authenticator.logout("Log out", "sidebar")
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

_pages = ["Upload & connect", "Executive summary", "LinkedIn deep dive", "Website (GA4)",
          "Cross-channel", "Audience", "Recommendations", "Data & export"]
if authenticator is not None and st.session_state.get("email") in config.auth_admins():
    _pages.append("Manage access")

page = st.radio(
    "Navigate", _pages,
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
elif page == "Manage access":
    admin_view.render(st.session_state.get("username"))

st.divider()
st.caption(
    "CyberproAI · Marketing Analytics — LinkedIn + Google Analytics. "
    "All figures computed directly from your data; the written analysis only describes them."
)
