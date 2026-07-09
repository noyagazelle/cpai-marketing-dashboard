"""
GA4 connection tester — run this to verify your live GA4 setup end-to-end.

    cd ~/cpai-marketing-dashboard
    .venv/bin/python check_ga4.py

It reads the same config the app uses (.env), runs one tiny query, and prints a
clear PASS or a specific, human-readable reason it failed. No data is changed.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import config
from connectors import ga4 as GA4


def main() -> int:
    print("── GA4 connection check ─────────────────────────────")
    stt = GA4.status()
    pid = config.ga4_property_id()
    creds = config.ga4_credentials_path() or ("(inline secrets)" if config.ga4_credentials_info() else None)

    print(f"Property ID           : {pid or 'MISSING'}")
    print(f"Service-account creds : {creds or 'MISSING'}")

    if not stt["configured"]:
        print(f"\n✗ Not configured: {stt['reason']}")
        print("  → Set GA4_PROPERTY_ID and GA4_SERVICE_ACCOUNT_JSON in .env (see README).")
        return 1

    # Tiny real query: total users over the last 7 days.
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    print(f"\nQuerying totalUsers for {start} → {end} …")
    try:
        client = GA4._client()
        df = GA4._run(client, pid, ["date"], ["totalUsers"], start, end)
    except Exception as e:
        msg = str(e)
        print(f"\n✗ Query failed: {type(e).__name__}: {msg}")
        low = msg.lower()
        if "permission" in low or "403" in low:
            print("  → The service-account email isn't a Viewer on this property.")
            print("    GA4 → Admin → Property Access Management → add the service-account")
            print("    email (…@….iam.gserviceaccount.com) with role Viewer.")
        elif "not found" in low or "404" in low or "invalid" in low and "propert" in low:
            print("  → Property ID looks wrong. Use the NUMERIC id from GA4 → Admin →")
            print("    Property Settings (not the G-XXXX measurement id).")
        elif "could not" in low or "credential" in low or "file" in low:
            print("  → Credentials file path/contents look wrong. Check GA4_SERVICE_ACCOUNT_JSON.")
        elif "disabled" in low or "has not been used" in low or "api" in low:
            print("  → Enable the 'Google Analytics Data API' in Google Cloud → APIs & Services.")
        return 2

    total = int(df["totalUsers"].sum()) if not df.empty else 0
    print(f"\n✓ PASS — connected. Last 7 days: {total:,} total users across {len(df)} day(s).")
    print("  You're wired up. Open the app → Website (GA4) tab → it will show ✓ Connected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
