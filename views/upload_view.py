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
        _cur = st.session_state.get("li_data", {})
        _is_sample = st.session_state.get("li_source", "").lower().startswith(("bundled", "sample"))
        _has_files = bool(_cur) and not _is_sample

        # Streamlit blanks a file_uploader whenever you leave the tab, which looked
        # like the files were lost. So once files are loaded we show THEM (by name)
        # and only bring the uploader back when the user asks to replace them.
        if st.session_state.get("li_notice"):
            st.info(st.session_state.pop("li_notice"))
        replacing = st.session_state.get("li_replace", False) or not _has_files
        uploads = None
        if _has_files and not replacing:
            with st.container(border=True):
                st.markdown(f"**📎 Loaded files** · {_period_label(_cur)}")
                for k in _cur:
                    st.markdown(f'{_pill(True, _cur[k].label)} &nbsp;`{_cur[k].source_name}`',
                                unsafe_allow_html=True)
                st.caption("These stay loaded — across tabs, reloads and restarts — and power every "
                           "other tab until you replace them.")
                if st.button("📤 Upload different files", key="li_replace_btn"):
                    st.session_state["li_replace"] = True
                    st.session_state.pop("li_sig", None)
                    st.rerun()
        else:
            uploads = st.file_uploader(
                "Drag & drop this period's LinkedIn .xls / .xlsx files",
                type=["xls", "xlsx", "xlsm"], accept_multiple_files=True, key="li_uploader",
            )
            if _has_files and st.button("Cancel — keep the current files", key="li_cancel_btn"):
                st.session_state["li_replace"] = False
                st.rerun()

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
                        # Always show the LATEST period, compared to the one before it. If
                        # this upload was an older period, it just joins the history.
                        latest = history.list_periods()[-1]
                        if latest["key"] != history.period_key(*period):
                            st.session_state["li_data"] = history.load_period(latest["key"])
                            st.session_state["li_source"] = (
                                f"saved period ({latest['start']} → {latest['end']})")
                            st.session_state["li_notice"] = (
                                f"Saved **{period[0]:%b %d} → {period[1]:%b %d, %Y}** to history. "
                                f"It's older than your latest period, so you're still viewing "
                                f"**{latest['start']} → {latest['end']}** — now compared against it.")
                    st.session_state["li_replace"] = False
                    st.session_state.pop("compare_key", None)
                    st.rerun()

        if _has_files:
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
            cur = loaders.linkedin_period(st.session_state.get("li_data", {}))
            cur_key = history.period_key(*cur) if cur else None
            cur_label = next((l for l, k in key_by_label.items() if k == cur_key), labels[-1])

            # What's being compared, in plain words — the default needs no clicks.
            _cur_start = next((p["start"] for p in periods if p["key"] == cur_key), None)
            _auto = history.previous_key(_cur_start) if _cur_start else None
            _cmp = st.session_state.get("compare_key") or _auto
            _cmp_label = next((l for l, k in key_by_label.items() if k == _cmp), None)
            if _cmp_label:
                st.success(f"📊 Viewing **{cur_label}**, compared against **{_cmp_label}**"
                           + ("" if st.session_state.get("compare_key") else " (automatic)") + ".")
            st.caption("Every upload is saved here automatically. The dashboard always shows the "
                       "**latest** period and compares it to the one saved **before** it — no "
                       "need to keep or re-upload old files.")

            adv = st.expander("Advanced: view or compare a different saved period")

            # 1) View ANY saved period as the current view (this session only —
            #    a fresh visit always opens on the latest period).
            view = adv.selectbox("View which period", labels, index=labels.index(cur_label),
                                 help="Load any saved period as the current view.")
            if key_by_label[view] != cur_key:
                st.session_state["li_data"] = history.load_period(key_by_label[view])
                _vp = loaders.linkedin_period(st.session_state["li_data"])
                st.session_state["li_source"] = (
                    f"saved period ({_vp[0]:%b %d} → {_vp[1]:%b %d, %Y})" if _vp else "saved period")
                st.session_state.pop("compare_key", None)
                st.rerun()

            # 2) Compare against ANY other saved period.
            others = [l for l in labels if l != view]
            if others:
                copts = ["Automatic (previous period)"] + others
                # keep the user's choice when they leave and return to this tab
                label_by_key = {k: l for l, k in key_by_label.items()}
                saved = label_by_key.get(st.session_state.get("compare_key"))
                choice = adv.selectbox("Compare against", copts,
                                      index=copts.index(saved) if saved in copts else 0,
                                      help="Any other saved period to use for the ▲/▼ changes.")
                st.session_state["compare_key"] = (None if choice == copts[0]
                                                   else key_by_label[choice])
                if st.session_state["compare_key"] is None:
                    st.session_state.pop("compare_key", None)

                # Explain silent "no comparison" cases instead of leaving the user guessing.
                view_p = next(p for p in periods if p["key"] == key_by_label[view])
                cmp_key = st.session_state.get("compare_key") or history.previous_key(view_p["start"])
                if cmp_key is None:
                    st.warning(f"**{view}** is your earliest saved period, so there's nothing "
                               "earlier to compare it to. Under **Advanced**, switch **View which "
                               "period** to a later period, or pick one under **Compare against**.")
                else:
                    cmp_p = next(p for p in periods if p["key"] == cmp_key)
                    if cmp_p["start"] <= view_p["end"] and view_p["start"] <= cmp_p["end"]:
                        st.caption(f"⚠️ These periods overlap ({view} vs {cmp_p['start']} → "
                                   f"{cmp_p['end']}), so some days are counted in both — changes "
                                   "will look smaller than they really are.")
            else:
                st.caption("Only one period saved so far — next period's upload will be compared "
                           "against it automatically.")

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
