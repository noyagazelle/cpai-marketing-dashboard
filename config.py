"""
Central configuration — reads settings from environment / .env / Streamlit
secrets, in that order of convenience. NEVER hardcode credentials here.

Recognised settings
--------------------
GA4_PROPERTY_ID              numeric GA4 property id, e.g. 123456789
GA4_SERVICE_ACCOUNT_JSON     path to the service-account key file
                             (or GOOGLE_APPLICATION_CREDENTIALS)
GA4_SERVICE_ACCOUNT_INFO     service-account key JSON, given inline as either a
                             Streamlit secrets table or a raw JSON-string env var
                             (for container deploys with no local key file, e.g.
                             the contents pulled from AWS Secrets Manager)
ANTHROPIC_API_KEY            optional — enables the AI narrative layer
AUTH_USERS                   per-user login credentials — a JSON string (or
                             Streamlit secrets table) shaped like
                             {"usernames": {"alice": {"name": "Alice",
                             "password": "<bcrypt hash>"}}}. Leave unset to
                             skip the login screen entirely (local dev).
AUTH_COOKIE_KEY              signing key for the login session cookie —
                             any random string, set once and keep stable.
AUTH_PRE_AUTHORIZED          JSON list of emails invited to self-register but
                             who haven't set a password yet, e.g.
                             ["newhire@company.com"]. An email is removed from
                             this list the moment that person registers.
AUTH_SECRET_ID               AWS Secrets Manager secret name/ARN holding
                             AUTH_USERS and AUTH_PRE_AUTHORIZED as JSON keys.
                             Set only on AWS deploys. When present, auth state
                             is read live from this secret (short-TTL cached,
                             not just read once at boot) instead of from
                             AUTH_USERS/AUTH_PRE_AUTHORIZED env vars — so
                             invites/registrations survive any redeploy, and
                             an edit made directly in Secrets Manager (e.g. a
                             bootstrap invite before anyone's registered) takes
                             effect within seconds, no restart needed.
"""
from __future__ import annotations

import json
import os
import time
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
    """Service-account JSON provided inline (for cloud deploys with no local key
    file) — either a Streamlit secrets table, or a raw JSON string in the
    GA4_SERVICE_ACCOUNT_INFO env var (e.g. injected from AWS Secrets Manager)."""
    val = _secret("GA4_SERVICE_ACCOUNT_INFO")
    if val:
        return dict(val)
    raw = os.environ.get("GA4_SERVICE_ACCOUNT_INFO")
    if raw:
        return json.loads(raw)
    return None


# --- Anthropic (optional, Milestone 5) ---
def anthropic_key() -> str | None:
    return get("ANTHROPIC_API_KEY")


def bedrock_model() -> str | None:
    """Bedrock inference-profile id, e.g. 'us.anthropic.claude-sonnet-4-6'. When
    set, the AI narrative uses Bedrock (IAM-authenticated, no API key) instead
    of a direct Anthropic API key."""
    return get("BEDROCK_MODEL_ID")


# --- Per-user authentication ---
def auth_users() -> dict | None:
    """Login credentials for streamlit-authenticator, e.g.
    {"usernames": {"alice": {"name": "Alice", "password": "<bcrypt hash>"}}}.
    None means no login screen (local dev with nothing configured)."""
    if auth_secret_id():
        raw = _secrets_manager_fetch().get("AUTH_USERS")
        return json.loads(raw) if raw else None
    val = _secret("AUTH_USERS")
    if val:
        return dict(val)
    raw = os.environ.get("AUTH_USERS")
    if raw:
        return json.loads(raw)
    return None


def auth_cookie_key() -> str:
    return get("AUTH_COOKIE_KEY", "cpai-marketing-dashboard-dev-key")


def auth_admins() -> list[str]:
    """Emails allowed to see/use "Manage access" (invite or remove people).
    Everyone else can still log in and use the dashboard, just not invite
    others. Empty means nobody sees the tab — set this explicitly."""
    if auth_secret_id():
        raw = _secrets_manager_fetch().get("AUTH_ADMINS")
        return json.loads(raw) if raw else []
    val = _secret("AUTH_ADMINS")
    if val:
        return list(val)
    raw = os.environ.get("AUTH_ADMINS")
    if raw:
        return json.loads(raw)
    return []


def set_auth_users(users: dict) -> None:
    """Persist an updated AUTH_USERS from the in-app "Manage access" page —
    updates the running process immediately, and durably either to .env
    (local) or the AUTH_SECRET_ID secret (AWS), so it survives a restart."""
    _persist_auth("AUTH_USERS", json.dumps(users))


def pre_authorized_emails() -> list[str]:
    """Emails invited to self-register (see AUTH_PRE_AUTHORIZED)."""
    if auth_secret_id():
        raw = _secrets_manager_fetch().get("AUTH_PRE_AUTHORIZED")
        return json.loads(raw) if raw else []
    val = _secret("AUTH_PRE_AUTHORIZED")
    if val:
        return list(val)
    raw = os.environ.get("AUTH_PRE_AUTHORIZED")
    if raw:
        return json.loads(raw)
    return []


def set_pre_authorized_emails(emails: list[str]) -> None:
    _persist_auth("AUTH_PRE_AUTHORIZED", json.dumps(emails))


def auth_secret_id() -> str | None:
    return get("AUTH_SECRET_ID")


def _persist_auth(key: str, raw: str) -> None:
    if auth_secret_id():
        _secrets_manager_upsert(key, raw)
    else:
        os.environ[key] = raw
        _upsert_env_line(key, raw)


_auth_secret_cache: dict = {"ts": 0.0, "data": None}
_AUTH_SECRET_TTL = 10  # seconds — short enough that a console edit is picked up quickly


def _secrets_manager_fetch() -> dict:
    """Current contents of the AUTH_SECRET_ID secret, cached briefly so every
    Streamlit rerun doesn't hit Secrets Manager on every click."""
    if _auth_secret_cache["data"] is not None and time.time() - _auth_secret_cache["ts"] < _AUTH_SECRET_TTL:
        return _auth_secret_cache["data"]
    import boto3
    client = boto3.client("secretsmanager")
    try:
        current = json.loads(client.get_secret_value(SecretId=auth_secret_id())["SecretString"])
    except client.exceptions.ResourceNotFoundException:
        current = {}
    _auth_secret_cache.update(ts=time.time(), data=current)
    return current


def _secrets_manager_upsert(key: str, value: str) -> None:
    """Merge one key into the AUTH_SECRET_ID JSON secret (AWS deploys)."""
    import boto3
    client = boto3.client("secretsmanager")
    secret_id = auth_secret_id()
    try:
        current = json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])
    except client.exceptions.ResourceNotFoundException:
        current = {}
    current[key] = value
    client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(current))
    _auth_secret_cache.update(ts=time.time(), data=current)  # keep this process's view instant


def _upsert_env_line(key: str, value: str) -> None:
    path = Path(__file__).parent / ".env"
    lines = path.read_text().splitlines() if path.exists() else []
    new_line = f"{key}={value}"
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n")


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
