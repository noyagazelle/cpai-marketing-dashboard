"""Upload & connect — the home base for loading each period's data.

LinkedIn exports and GA4 both get loaded here. Parsed LinkedIn data is stored in
st.session_state['li_data'] so every other view sees it regardless of which tab
the user is on; GA4 goes to st.session_state['ga4_data'] via the shared panel.
"""
from __future__ import annotations

import streamlit as st

import config
import history
import ui
import loaders
from parsing import KIND_LABELS
from views import ga4_view


def _pill(present: bool, label: str) -> str:
    cls = "ok" if present else "off"
    return f'<span class="cpai-pill {cls}">{"✓" if present else "—"} {label}</span>'


def _period_label(data: dict) -> str:
    ranges = [r.date_range for r in data.values() if r.date_range]
    if not ranges:
        return ""
    start = min(a for a, _ in ranges)
    end = max(b for _, b in ranges)
    return f"{start:%b %d, %Y} → {end:%b %d, %Y}"


def render():
    ui.section_header("Upload & connect",
                      "Load this period's data here. Everything else in the dashboard updates automatically.")

    col_li, col_ga4 = st.columns(2)

    # ------------------------------------------------------------------ #
    # LinkedIn
    # ------------------------------------------------------------------ #
    with col_li:
        st.markdown("### 1 · LinkedIn exports")
        st.caption("From your LinkedIn Company Page → **Analytics**, export **Visitors**, "
                   "**Followers**, and **Content/Updates** for the quarter, then drop them here. "
                   "Types are detected automatically — any subset works.")
        uploads = st.file_uploader(
            "Drag & drop this period's LinkedIn .xls / .xlsx files",
            type=["xls", "xlsx", "xlsm"], accept_multiple_files=True, key="li_uploader",
        )

        # Load new uploads once (detected by filename signature), then persist in
        # session AND archive to history so future periods can compare against it.
        if uploads:
            sig = tuple(sorted(f.name for f in uploads))
            if sig != st.session_state.get("li_sig"):
                parsed, errors = loaders.load_uploaded(uploads)
                for e in errors:
                    st.error(e)
                if parsed:
                    st.session_state["li_data"] = parsed
                    st.session_state["li_sig"] = sig
                    period = loaders.linkedin_period(parsed)
                    st.session_state["li_source"] = (
                        f"your uploaded files ({period[0]:%b %d} → {period[1]:%b %d, %Y})"
                        if period else f"your uploaded files ({len(uploads)} file(s))")
                    # Collect raw bytes keyed by detected kind.
                    raw = {}
                    for f in uploads:
                        for k, res in parsed.items():
                            if res.source_name == f.name:
                                raw[k] = (f.name, f.getvalue())
                                break
                    # ALWAYS mirror to disk so the upload survives a session reset,
                    # and archive as a dated period when the date range is detected.
                    history.save_current(raw)
                    if period:
                        history.save_period(raw, history.period_key(*period))
                    st.rerun()

        # Clear status of what's loaded — independent of the upload box above,
        # which Streamlit blanks when you switch tabs (that's normal, not data loss).
        _cur = st.session_state.get("li_data", {})
        _is_sample = st.session_state.get("li_source", "").lower().startswith(("bundled", "sample"))
        if _cur and not _is_sample:
            _kinds = ", ".join(_cur[k].label for k in _cur)
            st.success(f"✅ **Loaded & in use across every tab:** {_kinds}\n\n"
                       f"Source: {st.session_state.get('li_source', '')}")
            st.caption("ℹ️ The upload box above goes blank when you leave this tab and return — "
                       "that's normal Streamlit behaviour, **not** data loss. Your files stay loaded "
                       "and power all the other tabs. Drop new files above only to **replace** them.")
            if st.button("↺ Reset to sample data"):
                st.session_state["li_data"] = loaders.load_samples()
                st.session_state["li_source"] = "bundled sample data (June 2026)"
                st.session_state.pop("li_sig", None)
                history.clear_current()
                st.rerun()
        else:
            st.caption("Currently showing **sample data**. Upload your files above to replace it.")

        # Total followers — not in the export files, so take it from the LinkedIn page.
        default_total = int(st.session_state.get("total_followers") or config.follower_base() or 0)
        total_in = st.number_input(
            "Total followers (from your LinkedIn page)", min_value=0, step=1,
            value=default_total,
            help="The export files don't include your cumulative follower count, so enter the "
                 "number shown on your LinkedIn page. Used for the 'Total followers' and "
                 "'Period growth' figures. Update it each period.")
        if total_in:
            st.session_state["total_followers"] = int(total_in)

        # Saved periods + which one to compare the current period against.
        # Always shown (even when empty) so the feature is visible.
        st.markdown("**Saved periods** (for period-over-period)")
        periods = history.list_periods()
        if not periods:
            st.caption("📁 None saved yet. The sample data isn't saved — but every time you "
                       "**upload real LinkedIn files above, that period is stored here**. Once "
                       "you've uploaded two or more, each new period is automatically compared "
                       "against the previous one (the ▲/▼ changes become true period-over-period).")
        else:
            for p in periods:
                st.caption(f"• {p['start']} → {p['end']}  ·  {len(p['files'])} file(s)")

            # label -> key, for both selectors
            key_by_label = {f"{p['start']} → {p['end']}": p["key"] for p in periods}
            labels = list(key_by_label.keys())

            # 1) View ANY saved period as the current view.
            cur = loaders.linkedin_period(st.session_state.get("li_data", {}))
            cur_key = history.period_key(*cur) if cur else None
            cur_label = next((l for l, k in key_by_label.items() if k == cur_key), labels[-1])
            view = st.selectbox("View which period", labels, index=labels.index(cur_label),
                                help="Load any saved period as the current view.")
            if key_by_label[view] != cur_key:
                st.session_state["li_data"] = history.load_period(key_by_label[view])
                _vp = loaders.linkedin_period(st.session_state["li_data"])
                st.session_state["li_source"] = (
                    f"saved period ({_vp[0]:%b %d} → {_vp[1]:%b %d, %Y})" if _vp else "saved period")
                st.session_state.pop("li_sig", None)
                st.rerun()

            # 2) Compare against ANY other saved period.
            others = [l for l in labels if l != view]
            if others:
                copts = ["Automatic (previous period)"] + others
                choice = st.selectbox("Compare against", copts,
                                      help="Any other saved period to use for the ▲/▼ changes.")
                st.session_state["compare_key"] = (None if choice == copts[0]
                                                   else key_by_label[choice])
                if st.session_state["compare_key"] is None:
                    st.session_state.pop("compare_key", None)
            else:
                st.caption("Upload another period to compare across periods.")

    # ------------------------------------------------------------------ #
    # GA4
    # ------------------------------------------------------------------ #
    with col_ga4:
        st.markdown("### 2 · Website (GA4)")
        st.caption("Connect Google Analytics 4 live (service account in `.env`), or upload a "
                   "manual CSV/Excel export. Full setup steps are in the README.")
        ga4_view.connect_panel()

    st.divider()

    # ------------------------------------------------------------------ #
    # What's loaded
    # ------------------------------------------------------------------ #
    st.markdown("### What's loaded")
    data = st.session_state.get("li_data", {})
    ga4_data = st.session_state.get("ga4_data")
    st.markdown(
        " ".join(_pill(k in data, KIND_LABELS[k])
                 for k in ("followers", "visitors", "content", "competitors"))
        + " " + _pill(ga4_data is not None, "Website (GA4)"),
        unsafe_allow_html=True,
    )
    if data:
        period = _period_label(data)
        src = st.session_state.get("li_source", "")
        st.caption(f"LinkedIn source: {src}" + (f" · period: **{period}**" if period else ""))
        cols = st.columns(len(data))
        for col, (kind, res) in zip(cols, data.items()):
            with col:
                st.markdown(f"**{res.label}**")
                dr = res.date_range
                if dr:
                    st.caption(f"📅 {dr[0]:%b %d} → {dr[1]:%b %d, %Y} ({(dr[1]-dr[0]).days + 1} days)")
                for w in res.warnings:
                    st.warning(w, icon="⚠️")

    if not data and ga4_data is None:
        st.info("Nothing loaded yet. Upload LinkedIn files or connect GA4 above to begin.")
    else:
        st.success("Ready — head to **Executive summary** for the headline takeaways, or any "
                   "other tab for the detail.")
