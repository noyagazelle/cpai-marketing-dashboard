"""
Reusable Plotly chart builders — every chart in the app goes through here so
styling stays consistent and on-brand. All functions return a go.Figure.
"""
from __future__ import annotations

import plotly.graph_objects as go

import branding as B


def _apply(fig: go.Figure, title: str | None = None, height: int = 320) -> go.Figure:
    fig.update_layout(**B.PLOTLY_LAYOUT, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=15)))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", zeroline=False)
    return fig


def line(df, x, ys, title=None, labels=None, height=320, fill=False):
    """Line (optionally area) chart for one or more y-series."""
    labels = labels or {}
    fig = go.Figure()
    ys = ys if isinstance(ys, (list, tuple)) else [ys]
    for y in ys:
        fig.add_trace(
            go.Scatter(
                x=df[x], y=df[y], mode="lines", name=labels.get(y, y),
                line=dict(width=2.5),
                fill="tozeroy" if fill and len(ys) == 1 else None,
                hovertemplate="%{x|%b %d}: %{y:,.0f}<extra></extra>",
            )
        )
    return _apply(fig, title, height)


def stacked_area(df, x, ys, title=None, labels=None, height=320):
    labels = labels or {}
    fig = go.Figure()
    for y in ys:
        fig.add_trace(
            go.Scatter(
                x=df[x], y=df[y], mode="lines", name=labels.get(y, y),
                stackgroup="one", line=dict(width=0.5),
                hovertemplate="%{x|%b %d}: %{y:,.0f}<extra></extra>",
            )
        )
    return _apply(fig, title, height)


def bars(df, x, y, title=None, height=320, color=None, percent=False):
    fig = go.Figure(
        go.Bar(
            x=df[x], y=df[y],
            marker_color=color or B.CYAN,
            hovertemplate=("%{x}: %{y:.1%}" if percent else "%{x}: %{y:,.0f}") + "<extra></extra>",
        )
    )
    if percent:
        fig.update_yaxes(tickformat=".0%")
    return _apply(fig, title, height)


def hbars(labels, values, title=None, height=None, percent=False, color=None):
    """Horizontal bar — ideal for demographic breakdowns. Sorted ascending for display."""
    height = height or max(220, 26 * len(labels) + 80)
    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h",
            marker_color=color or B.TEAL,
            hovertemplate=("%{y}: %{x:.1%}" if percent else "%{y}: %{x:,.0f}") + "<extra></extra>",
        )
    )
    if percent:
        fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(showgrid=False)
    return _apply(fig, title, height)


def donut(labels, values, title=None, height=300):
    fig = go.Figure(
        go.Pie(
            labels=labels, values=values, hole=0.62,
            marker=dict(colors=B.CHART_SEQUENCE),
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>",
        )
    )
    return _apply(fig, title, height)


def dual_axis(df, x, y1, y2, y1_label=None, y2_label=None, title=None, height=340,
              markers_x=None):
    """Two series on independent y-axes — for comparing a driver vs an outcome.
    Optionally drop vertical dotted markers at `markers_x` dates (e.g. post days)."""
    from plotly.subplots import make_subplots
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df[x], y=df[y1], name=y1_label or y1, mode="lines",
                             line=dict(width=2.5, color=B.CYAN)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df[x], y=df[y2], name=y2_label or y2, mode="lines",
                             line=dict(width=2.5, color=B.TEAL)), secondary_y=True)
    fig.update_layout(**B.PLOTLY_LAYOUT, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=15)))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title_text=y1_label or y1, secondary_y=False,
                     showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(title_text=y2_label or y2, secondary_y=True, showgrid=False)
    if markers_x is not None:
        for mx in markers_x:
            fig.add_vline(x=mx, line_width=1, line_dash="dot", line_color="rgba(255,255,255,0.25)")
    return fig


def scatter(df, x, y, text=None, title=None, height=340, size=None):
    fig = go.Figure(
        go.Scatter(
            x=df[x], y=df[y], mode="markers",
            marker=dict(size=size if size is not None else 12, color=B.CYAN,
                        line=dict(width=1, color=B.NAVY)),
            text=df[text] if text else None,
            hovertemplate=(f"{text}: " + "%{text}<br>" if text else "") +
                          f"{x}: " + "%{x}<br>" + f"{y}: " + "%{y}<extra></extra>",
        )
    )
    return _apply(fig, title, height)
