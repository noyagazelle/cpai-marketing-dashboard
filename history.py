"""
Period history — persists each uploaded LinkedIn period so the dashboard can
compare the current period against previous ones (true period-over-period).

Storage backend is automatic:
  * Local disk (history/<key>/<kind>.<ext>) when running on your machine.
  * Amazon S3 (s3://<S3_BUCKET>/history/...) when S3_BUCKET is set — used on
    AWS container deploys, where the local filesystem is wiped on restart.
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
# Storage backend — picked automatically:
#   * GitHub repo (data branch) when GITHUB_TOKEN + GITHUB_REPO are set
#   * Amazon S3 when S3_BUCKET is set
#   * Google Cloud Storage when GCS_BUCKET is set
#   * local disk otherwise (default on your own machine)
# All four primitives below (_write/_read/_list/_delete) dispatch on the backend.
# --------------------------------------------------------------------------- #

# ---- Amazon S3 ----
def _s3_bucket_name() -> Optional[str]:
    return config.get("S3_BUCKET")


def _use_s3() -> bool:
    return bool(_s3_bucket_name())


def _s3_client():
    import boto3
    return boto3.client("s3")


# ---- Google Cloud Storage ----
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


# ---- GitHub (free, no billing) ----
_GH_API = "https://api.github.com"
_gh_tree_cache: dict = {"ts": 0.0, "tree": None}


def _gh_conf():
    return (config.get("GITHUB_TOKEN"), config.get("GITHUB_REPO"),
            config.get("GITHUB_BRANCH", "main"))


def _use_github() -> bool:
    tok, repo, _ = _gh_conf()
    return bool(tok and repo)


def _gh_headers():
    tok, _, _ = _gh_conf()
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}


def _gh_ensure_branch():
    import base64, requests
    _, repo, branch = _gh_conf()
    if requests.get(f"{_GH_API}/repos/{repo}/branches/{branch}",
                    headers=_gh_headers()).status_code == 200:
        return
    info = requests.get(f"{_GH_API}/repos/{repo}", headers=_gh_headers()).json()
    default = info.get("default_branch", "main")
    ref = requests.get(f"{_GH_API}/repos/{repo}/git/ref/heads/{default}", headers=_gh_headers())
    if ref.status_code != 200:
        # Empty repo (no commits) — create an initial commit on the default branch.
        requests.put(f"{_GH_API}/repos/{repo}/contents/.init", headers=_gh_headers(),
                     json={"message": "initialise data store",
                           "content": base64.b64encode(b"cpai-marketing data store\n").decode()})
        ref = requests.get(f"{_GH_API}/repos/{repo}/git/ref/heads/{default}", headers=_gh_headers())
        if ref.status_code != 200:
            return
    if branch != default:
        requests.post(f"{_GH_API}/repos/{repo}/git/refs", headers=_gh_headers(),
                      json={"ref": f"refs/heads/{branch}", "sha": ref.json()["object"]["sha"]})


def _gh_get(relpath: str):
    """(bytes, sha) for history/<relpath>, or (None, None)."""
    import requests
    _, repo, branch = _gh_conf()
    r = requests.get(f"{_GH_API}/repos/{repo}/contents/history/{relpath}",
                     headers=_gh_headers(), params={"ref": branch})
    if r.status_code != 200:
        return None, None
    import base64
    j = r.json()
    return base64.b64decode(j["content"]), j["sha"]


def _gh_tree() -> list[str]:
    import time
    if _gh_tree_cache["tree"] is not None and time.time() - _gh_tree_cache["ts"] < 15:
        return _gh_tree_cache["tree"]
    import requests
    _, repo, branch = _gh_conf()
    r = requests.get(f"{_GH_API}/repos/{repo}/git/trees/{branch}",
                     headers=_gh_headers(), params={"recursive": "1"})
    tree = ([t["path"] for t in r.json().get("tree", []) if t["type"] == "blob"]
            if r.status_code == 200 else [])
    _gh_tree_cache.update(ts=time.time(), tree=tree)
    return tree


# ---- Dispatchers ----
def _write_bytes(relpath: str, blob: bytes):
    if _use_github():
        import base64, requests
        _, repo, branch = _gh_conf()
        _gh_ensure_branch()
        _, sha = _gh_get(relpath)
        payload = {"message": f"data: update {relpath}",
                   "content": base64.b64encode(blob).decode(), "branch": branch}
        if sha:
            payload["sha"] = sha
        requests.put(f"{_GH_API}/repos/{repo}/contents/history/{relpath}",
                     headers=_gh_headers(), json=payload)
        _gh_tree_cache["tree"] = None
    elif _use_s3():
        _s3_client().put_object(Bucket=_s3_bucket_name(), Key=f"history/{relpath}", Body=blob)
    elif _use_gcs():
        _gcs_bucket().blob(f"history/{relpath}").upload_from_string(blob)
    else:
        p = HISTORY_DIR / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)


def _read_bytes(relpath: str) -> Optional[bytes]:
    if _use_github():
        return _gh_get(relpath)[0]
    if _use_s3():
        client = _s3_client()
        try:
            return client.get_object(Bucket=_s3_bucket_name(), Key=f"history/{relpath}")["Body"].read()
        except client.exceptions.NoSuchKey:
            return None
    if _use_gcs():
        b = _gcs_bucket().blob(f"history/{relpath}")
        return b.download_as_bytes() if b.exists() else None
    p = HISTORY_DIR / relpath
    return p.read_bytes() if p.exists() else None


def _list_paths(prefix: str) -> list[str]:
    """Relative paths (below the history root) under `prefix`."""
    if _use_github():
        pre = f"history/{prefix}"
        return [p[len("history/"):] for p in _gh_tree() if p.startswith(pre)]
    if _use_s3():
        client = _s3_client()
        paginator = client.get_paginator("list_objects_v2")
        paths = []
        for page in paginator.paginate(Bucket=_s3_bucket_name(), Prefix=f"history/{prefix}"):
            paths.extend(o["Key"][len("history/"):] for o in page.get("Contents", []))
        return paths
    if _use_gcs():
        it = _gcs_bucket().list_blobs(prefix=f"history/{prefix}")
        return [b.name[len("history/"):] for b in it if not b.name.endswith("/")]
    base = HISTORY_DIR / prefix
    if not base.exists():
        return []
    return [str(f.relative_to(HISTORY_DIR)) for f in base.rglob("*") if f.is_file()]


def _delete_prefix(prefix: str):
    if _use_github():
        import requests
        _, repo, branch = _gh_conf()
        for rel in _list_paths(prefix):
            _, sha = _gh_get(rel)
            if sha:
                requests.request("DELETE",
                                 f"{_GH_API}/repos/{repo}/contents/history/{rel}",
                                 headers=_gh_headers(),
                                 json={"message": f"data: delete {rel}", "sha": sha, "branch": branch})
        _gh_tree_cache["tree"] = None
    elif _use_s3():
        keys = _list_paths(prefix)
        if keys:
            client = _s3_client()
            client.delete_objects(Bucket=_s3_bucket_name(),
                                  Delete={"Objects": [{"Key": f"history/{k}"} for k in keys]})
    elif _use_gcs():
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
