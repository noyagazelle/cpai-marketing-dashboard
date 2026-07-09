"""Shared LinkedIn-export loaders (used by the upload view and app startup)."""
from __future__ import annotations

from pathlib import Path

from parsing import parse_linkedin, ParsedLinkedIn

SAMPLE_DIR = Path(__file__).parent / "sample_data"


def load_uploaded(files) -> tuple[dict[str, ParsedLinkedIn], list[str]]:
    """Parse uploaded files → ({kind: ParsedLinkedIn}, [error messages])."""
    parsed: dict[str, ParsedLinkedIn] = {}
    errors: list[str] = []
    for f in files:
        try:
            res = parse_linkedin(f, source_name=f.name)
            parsed[res.kind] = res  # last file of a kind wins
        except Exception as e:  # fail loudly, per file
            errors.append(f"Could not parse **{f.name}**: {e}")
    return parsed, errors


def linkedin_period(li_data: dict[str, ParsedLinkedIn]):
    """Overall (start_date, end_date) covered by the loaded LinkedIn data, or None."""
    ranges = [r.date_range for r in li_data.values() if r.date_range]
    if not ranges:
        return None
    start = min(a for a, _ in ranges)
    end = max(b for _, b in ranges)
    return start.date(), end.date()


def load_samples() -> dict[str, ParsedLinkedIn]:
    parsed: dict[str, ParsedLinkedIn] = {}
    for p in sorted(SAMPLE_DIR.glob("*.xls*")):
        try:
            with open(p, "rb") as fh:
                res = parse_linkedin(fh, source_name=p.name)
            parsed[res.kind] = res
        except Exception:
            pass
    return parsed
