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


def takeaway(text: str, tone: str = "neutral"):
    """Render a prioritized takeaway as a colored left-border callout."""
    color = {"good": B.GOOD, "bad": B.BAD, "neutral": B.CYAN}.get(tone, B.CYAN)
    st.markdown(
        f'<div style="border-left:4px solid {color}; background:{B.SURFACE}; '
        f'border:1px solid {B.BORDER}; border-left:4px solid {color}; color:{B.INK}; '
        f'padding:10px 14px; margin:6px 0; border-radius:0 8px 8px 0;">{_md_bold(text)}</div>',
        unsafe_allow_html=True,
    )
