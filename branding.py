"""
Central branding config — change everything about the look here.

Softer-dark theme built on the CyberproAI accent palette (slate, not black).
To rebrand: swap the hex values, the LOGO_PATH, and COMPANY_NAME.
Nothing else in the app hardcodes a color.
"""
from pathlib import Path

COMPANY_NAME = "CyberproAI"
DASHBOARD_TITLE = "Marketing Analytics Dashboard"
LOGO_PATH = str(Path(__file__).parent / "assets" / "logo.svg")

# --- Core palette (softer dark, CyberproAI accents) ---
BG = "#1B2433"          # page background (slate, not black)
SURFACE = "#232E40"     # card background (lighter slate)
CYAN = "#2DBCDF"        # primary accent
TEAL = "#26DFC6"        # secondary accent
TEAL_2 = "#0AC2AC"      # tertiary accent
INK = "#E6EDF3"         # primary text (light)
MUTED = "#94A3B8"       # secondary text
BORDER = "rgba(255,255,255,0.10)"
GOOD = "#26DFC6"        # positive delta (teal, reads on dark)
BAD = "#F87171"         # negative delta
WARN = "#FBBF24"        # caution / insufficient data

# Kept for chart marker outlines etc.
NAVY = "#0B1220"
NAVY_2 = "#232E40"

# Ordered accent sequence for multi-series charts
CHART_SEQUENCE = [CYAN, TEAL, TEAL_2, "#7C9CF0", "#F0A6CA", "#FBBF24", "#9AE6B4"]

# Plotly layout defaults so every chart is consistent & on-brand
PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK, family="Inter, -apple-system, Segoe UI, sans-serif", size=13),
    colorway=CHART_SEQUENCE,
    margin=dict(l=10, r=10, t=40, b=10),
    hoverlabel=dict(bgcolor=SURFACE, font_size=12, font_color=INK,
                    bordercolor="rgba(255,255,255,0.15)"),
    legend=dict(orientation="h", y=-0.2),
)

# Injected CSS — typography, spacing, KPI cards, top-nav tabs
CUSTOM_CSS = f"""
<style>
  .stApp {{ background: {BG}; }}
  h1, h2, h3, h4 {{ color: {INK}; font-weight: 700; letter-spacing:-0.01em; }}
  .block-container {{ padding-top: 2rem; max-width: 1240px; }}
  [data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}

  .cpai-kpi {{
      background: {SURFACE};
      border: 1px solid {BORDER};
      border-radius: 14px; padding: 18px 20px; height: 100%;
      box-shadow: 0 1px 3px rgba(0,0,0,0.25);
  }}
  .cpai-kpi .label {{ color: {MUTED}; font-size: 0.8rem; text-transform: uppercase;
      letter-spacing: 0.06em; margin-bottom: 6px; }}
  .cpai-kpi .value {{ color: {INK}; font-size: 1.9rem; font-weight: 700; line-height:1; }}
  .cpai-kpi .delta-up {{ color: {GOOD}; font-size: 0.85rem; font-weight:600; }}
  .cpai-kpi .delta-down {{ color: {BAD}; font-size: 0.85rem; font-weight:600; }}
  .cpai-kpi .delta-flat {{ color: {MUTED}; font-size: 0.85rem; }}

  .cpai-pill {{ display:inline-block; padding:3px 10px; border-radius:999px;
      font-size:0.75rem; font-weight:600; margin-right:6px; }}
  .cpai-pill.ok   {{ background: rgba(38,223,198,0.15); color:{TEAL}; }}
  .cpai-pill.warn {{ background: rgba(251,191,36,0.15); color:{WARN}; }}
  .cpai-pill.off  {{ background: rgba(148,163,184,0.15); color:{MUTED}; }}

  /* Top navigation: render the horizontal radio as clear clickable tabs */
  div[role="radiogroup"] {{ gap: 6px; flex-wrap: wrap; }}
  div[role="radiogroup"] label {{
      background: {SURFACE}; border: 1px solid {BORDER};
      border-radius: 10px; padding: 8px 16px; margin: 0; cursor: pointer;
      transition: all 0.15s ease;
  }}
  div[role="radiogroup"] label:hover {{ border-color: {CYAN}; }}
  div[role="radiogroup"] label:has(input:checked) {{
      background: linear-gradient(180deg, rgba(45,188,223,0.22), rgba(38,223,198,0.10));
      border-color: {CYAN};
  }}
  div[role="radiogroup"] label p {{ font-weight: 600; font-size: 0.95rem; color: {INK}; }}
  /* hide the little radio dot so it reads as a tab, not a form control */
  div[role="radiogroup"] label > div:first-child {{ display: none; }}
</style>
"""
