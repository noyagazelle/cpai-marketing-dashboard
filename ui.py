"""Shared UI helpers — KPI cards, number/delta formatting, small components."""
from __future__ import annotations

import re
from typing import Optional

import streamlit as st

import branding as B


def _md_bold(text: str) -> str:
    """Convert **bold** to <strong> — Markdown isn't parsed inside raw-HTML blocks."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def fmt_int(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}"


def fmt_pct(v, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{digits}f}%"


def _delta_html(delta: Optional[float], context: str = "") -> str:
    if delta is None:
        # no comparison available — show only the context note (or a blank spacer)
        return f'<div class="delta-flat">{context or "&nbsp;"}</div>'
    ctx = f" · {context}" if context else ""
    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "▬")
    cls = "delta-up" if delta > 0 else ("delta-down" if delta < 0 else "delta-flat")
    return f'<div class="{cls}">{arrow} {abs(delta) * 100:.1f}%{ctx}</div>'


def kpi(col, label: str, value: str, delta: Optional[float] = None, context: str = "",
        hint: str = ""):
    """Render a KPI card. `delta` is a fraction (0.12 = +12%); context labels it.
    `hint` is a short plain-English description of what the number means."""
    hint_html = (f'<div style="color:{B.MUTED}; font-size:0.72rem; margin-top:6px; '
                 f'line-height:1.25;">{hint}</div>') if hint else ""
    col.markdown(
        f"""
        <div class="cpai-kpi">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            {_delta_html(delta, context)}
            {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str = ""):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def note(text: str, kind: str = "info"):
    icons = {"info": "ℹ️", "warn": "⚠️", "ok": "✅"}
    st.caption(f"{icons.get(kind, 'ℹ️')} {text}")


def _fmt_change(r) -> str:
    pct = r["% change"]
    pct_txt = f" ({pct:+.0%})" if pct is not None and pct == pct else (" (new)" if r["Change"] > 0 else "")
    return f"{r['Trend'].split()[0]} {r['Change']:+,.0f}{pct_txt}"


def change_table(df, prev_label: str = "", compact: bool = False):
    """Render a per-category period-over-period table (from analysis.compare.change_table)
    with ▲ green / ▼ red / = grey. `compact` drops the Previous column for narrow layouts."""
    if df is None or df.empty:
        return
    label_c = df.columns[0]
    show = df.copy()
    show["Change"] = show.apply(_fmt_change, axis=1)
    prev_col = f"Previous ({prev_label})" if prev_label else "Previous"
    show = show.rename(columns={"Previous": prev_col})
    show = show[[label_c, "Now", "Change"] if compact else [label_c, "Now", prev_col, "Change"]]

    def _color(v):
        s = str(v)
        if s.startswith("▲"):
            return f"color: {B.GOOD}; font-weight: 600"
        if s.startswith("▼"):
            return f"color: {B.BAD}; font-weight: 600"
        return f"color: {B.MUTED}"

    st.dataframe(
        show.style.map(_color, subset=["Change"]).format({"Now": "{:,.0f}", prev_col: "{:,.0f}"}),
        use_container_width=True, hide_index=True,
    )


def takeaway(text: str, tone: str = "neutral"):
    """Render a prioritized takeaway as a colored left-border callout."""
    color = {"good": B.GOOD, "bad": B.BAD, "neutral": B.CYAN}.get(tone, B.CYAN)
    st.markdown(
        f'<div style="border-left:4px solid {color}; background:{B.SURFACE}; '
        f'border:1px solid {B.BORDER}; border-left:4px solid {color}; color:{B.INK}; '
        f'padding:10px 14px; margin:6px 0; border-radius:0 8px 8px 0;">{_md_bold(text)}</div>',
        unsafe_allow_html=True,
    )
