"""
Central configuration — reads settings from environment / .env / Streamlit
secrets, in that order of convenience. NEVER hardcode credentials here.

Recognised settings
--------------------
GA4_PROPERTY_ID              numeric GA4 property id, e.g. 123456789
GA4_SERVICE_ACCOUNT_JSON     path to the service-account key file
                             (or GOOGLE_APPLICATION_CREDENTIALS)
ANTHROPIC_API_KEY            optional — enables the AI narrative layer
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

# Streamlit secrets (used when deployed) are read lazily to avoid a hard
# dependency at import time.
def _secret(key: str):
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None


def get(key: str, default=None):
    """Env var first, then Streamlit secrets, then default."""
    return os.environ.get(key) or _secret(key) or default


# --- GA4 ---
def ga4_property_id() -> str | None:
    return get("GA4_PROPERTY_ID")


def ga4_credentials_path() -> str | None:
    return get("GA4_SERVICE_ACCOUNT_JSON") or get("GOOGLE_APPLICATION_CREDENTIALS")


def ga4_credentials_info() -> dict | None:
    """Service-account JSON provided inline via secrets (for cloud deploys)."""
    val = _secret("GA4_SERVICE_ACCOUNT_INFO")
    if val:
        return dict(val)
    return None


# --- Anthropic (optional, Milestone 5) ---
def anthropic_key() -> str | None:
    return get("ANTHROPIC_API_KEY")


# --- LinkedIn: true total follower count (not in the export files) ---
def follower_base() -> int | None:
    """The actual total-followers number (shown on the LinkedIn page). Used to
    replace the demographic-sum estimate. Set TOTAL_FOLLOWERS in .env, or enter
    it in the app on the Upload & connect tab."""
    v = get("TOTAL_FOLLOWERS")
    try:
        return int(str(v).replace(",", "")) if v else None
    except (TypeError, ValueError):
        return None


# --- Default reporting window: last 28 complete days vs the prior 28 ---
def default_period(days: int = 28) -> tuple[date, date]:
    end = date.today() - timedelta(days=1)  # yesterday (last complete day)
    start = end - timedelta(days=days - 1)
    return start, end


def previous_period(start: date, end: date) -> tuple[date, date]:
    length = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    return prev_start, prev_end
