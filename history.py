"""
Period history — persists each uploaded LinkedIn period so the dashboard can
compare the current period against previous ones (true period-over-period).

Storage backend is automatic:
  * Local disk (history/<key>/<kind>.<ext>) when running on your machine.
  * Google Cloud Storage (gs://<GCS_BUCKET>/history/...) when GCS_BUCKET is set —
    used on Streamlit Cloud, where the local filesystem is wiped on restart.

Same public API either way: save_period / list_periods / load_period /
save_current / load_current / clear_current / previous_key.
Files are stored raw (re-parsable) at "<key>/<kind>.<ext>", plus the durable
"_current/" working set.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

import config
from parsing import parse_linkedin, ParsedLinkedIn

HISTORY_DIR = Path(__file__).parent / "history"
_CURRENT = "_current"


# --------------------------------------------------------------------------- #
# Storage backend (local disk OR Google Cloud Storage)
# --------------------------------------------------------------------------- #
def _bucket_name() -> Optional[str]:
    return config.get("GCS_BUCKET")


def _use_gcs() -> bool:
    return bool(_bucket_name())


def _gcs_bucket():
    from google.cloud import storage
    from google.oauth2 import service_account
    info = config.ga4_credentials_info()
    path = config.ga4_credentials_path()
    project = None
    creds = None
    if info:
        creds = service_account.Credentials.from_service_account_info(info)
        project = info.get("project_id")
    elif path:
        creds = service_account.Credentials.from_service_account_file(path)
    client = storage.Client(credentials=creds, project=project)
    return client.bucket(_bucket_name())


def _write_bytes(relpath: str, blob: bytes):
    if _use_gcs():
        _gcs_bucket().blob(f"history/{relpath}").upload_from_string(blob)
    else:
        p = HISTORY_DIR / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)


def _read_bytes(relpath: str) -> Optional[bytes]:
    if _use_gcs():
        b = _gcs_bucket().blob(f"history/{relpath}")
        return b.download_as_bytes() if b.exists() else None
    p = HISTORY_DIR / relpath
    return p.read_bytes() if p.exists() else None


def _list_paths(prefix: str) -> list[str]:
    """Relative paths (below the history root) under `prefix`."""
    if _use_gcs():
        it = _gcs_bucket().list_blobs(prefix=f"history/{prefix}")
        return [b.name[len("history/"):] for b in it if not b.name.endswith("/")]
    base = HISTORY_DIR / prefix
    if not base.exists():
        return []
    return [str(f.relative_to(HISTORY_DIR)) for f in base.rglob("*") if f.is_file()]


def _delete_prefix(prefix: str):
    if _use_gcs():
        for b in _gcs_bucket().list_blobs(prefix=f"history/{prefix}"):
            b.delete()
    else:
        base = HISTORY_DIR / prefix
        if base.exists():
            for f in base.rglob("*"):
                if f.is_file():
                    f.unlink()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def period_key(start: date, end: date) -> str:
    return f"{start:%Y-%m-%d}_{end:%Y-%m-%d}"


def _save(folder: str, raw_files: dict[str, tuple[str, bytes]]):
    _delete_prefix(f"{folder}/")
    for kind, (fname, blob) in raw_files.items():
        ext = Path(fname).suffix or ".xls"
        _write_bytes(f"{folder}/{kind}{ext}", blob)


def _load(folder: str) -> dict[str, ParsedLinkedIn]:
    data: dict[str, ParsedLinkedIn] = {}
    for rel in sorted(_list_paths(f"{folder}/")):
        if ".xls" not in rel.lower():
            continue
        blob = _read_bytes(rel)
        if blob is None:
            continue
        try:
            res = parse_linkedin(io.BytesIO(blob), source_name=Path(rel).name)
            data[res.kind] = res
        except Exception:
            pass
    return data


def save_period(raw_files: dict[str, tuple[str, bytes]], key: str):
    _save(key, raw_files)


def load_period(key: str) -> dict[str, ParsedLinkedIn]:
    return _load(key)


def save_current(raw_files: dict[str, tuple[str, bytes]]):
    """Durable copy of the latest upload — survives session/server resets."""
    _save(_CURRENT, raw_files)


def load_current() -> dict[str, ParsedLinkedIn]:
    return _load(_CURRENT)


def clear_current():
    _delete_prefix(f"{_CURRENT}/")


def list_periods() -> list[dict]:
    """All stored periods, oldest first: [{key, start, end, files}]."""
    keys: dict[str, list[str]] = {}
    for rel in _list_paths(""):
        parts = rel.split("/")
        if len(parts) < 2:
            continue
        key = parts[0]
        if key == _CURRENT or "_" not in key:
            continue
        try:
            date.fromisoformat(key.split("_", 1)[0])  # validate the start date
        except ValueError:
            continue
        keys.setdefault(key, []).append(parts[-1])
    out = []
    for key, files in keys.items():
        s, e = key.split("_", 1)
        out.append({"key": key, "start": s, "end": e, "files": sorted(files)})
    return sorted(out, key=lambda x: x["start"])


def previous_key(current_start: str, override: Optional[str] = None) -> Optional[str]:
    """Key of the period to compare against: an explicit choice (any period),
    else the most recent stored period starting before `current_start`."""
    periods = list_periods()
    keys = {p["key"] for p in periods}
    if override and override in keys and override != period_key_of(current_start):
        return override
    earlier = [p for p in periods if p["start"] < current_start]
    return earlier[-1]["key"] if earlier else None


def period_key_of(start_str: str) -> str:
    for p in list_periods():
        if p["start"] == start_str:
            return p["key"]
    return ""
