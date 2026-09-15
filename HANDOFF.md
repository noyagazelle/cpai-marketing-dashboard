# Handoff — CyberPro AI Marketing Analytics Dashboard

Short, practical owner's guide. For full detail see [`README.md`](README.md).

## What this is
An internal Streamlit dashboard that turns **LinkedIn company-page exports** and **GA4**
website data into KPIs, a written executive analysis, and prioritized recommendations for
leadership. All numbers are computed deterministically from your files; the optional AI layer
only *phrases* those verified numbers.

## Where it lives & how to run it
- Folder: **`~/cpai-marketing-dashboard`** (kept outside iCloud on purpose — see Gotchas).
- Run:
  ```bash
  cd ~/cpai-marketing-dashboard
  .venv/bin/streamlit run app.py
  ```
- Permanent link: **http://localhost:8501** (same every time — keep the tab open, just refresh).
- Stop: `Ctrl+C` in the terminal.
- First-time setup on a new machine: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

## The quarterly routine (the whole job)
1. Export from LinkedIn (Company Page → Analytics): **Visitors**, **Followers**,
   **Content/Updates**.
2. Open the app → **Upload & connect** tab → drop the LinkedIn files in. Confirm the detected
   **period** is the quarter you meant.
3. GA4: click **Refresh** (if connected live) or upload a GA4 CSV/Excel export in the same tab.
4. Review **Executive summary** and **Recommendations**; export any tables from **Data & export**.

Uploading new files replaces the working set and recomputes everything automatically.

## Credentials (never commit these)
Set in `.env` locally (copy `.env.example`), or as container env vars / Streamlit Cloud
**Secrets** when deployed:
- `GA4_PROPERTY_ID` — numeric GA4 property id.
- `GA4_SERVICE_ACCOUNT_JSON` — path to the service-account key file (local), or
  `GA4_SERVICE_ACCOUNT_INFO` inline in cloud secrets/env vars.
- `ANTHROPIC_API_KEY` — optional; enables the AI-written analysis. Without it, a rule-based
  narrative is used. Get one at <https://console.anthropic.com>.
- `AUTH_PRE_AUTHORIZED` / `AUTH_USERS` — login. Invite emails via the first, people register
  their own password via the app, the second fills in automatically. See README → *Access
  control*.

GA4 setup is a one-time task — full step-by-step in `README.md` → *GA4 setup*.

## Live deployment (AWS)
This app is deployed on **AWS Lightsail**, account `706124985445`, region `us-east-1`.
Everything is tagged `project: marketing-dashboard`. The Lightsail service and S3 bucket are
findable via the tagging API (IAM resources aren't covered by it, so check those separately):
```bash
aws resourcegroupstaggingapi get-resources --tag-filters Key=project,Values=marketing-dashboard
aws iam list-user-tags --user-name marketing-dashboard-app   # confirms the IAM user's tag
```
- **Lightsail container service**: `marketing-dashboard` — the running app.
- **S3 bucket**: `marketing-dashboard-history-706124985445` — durable LinkedIn upload history
  (survives redeploys; local disk inside the container does not). Versioning is on (protects
  against an accidental overwrite/delete), with a lifecycle rule expiring old versions after 90
  days so this never accumulates real storage cost.
- **IAM user**: `marketing-dashboard-app` — scoped to only that one bucket (plus Bedrock invoke
  below); its access key is passed to the container as env vars (Lightsail has no IAM roles,
  unlike ECS).
- **Bedrock application inference profile**: `marketing-dashboard` (Claude Sonnet 4.6) — powers
  the AI-written executive narrative; used via `BEDROCK_MODEL_ID` instead of a direct Anthropic
  API key.
- **Budget alert**: `marketing-dashboard`, $25/month threshold, filtered to this project's
  tagged spend only — emails `sefi.c@cyberpro-ai.com` at 80% actual and 100% forecasted.
- **Resource group**: `marketing-dashboard` — one console view of every taggable resource above
  (AWS console → Resource Groups & Tag Editor → Saved Resource Groups).

Redeploy steps and the auth-persistence caveat (invites reset on redeploy — copy `AUTH_USERS`
forward manually) are in `README.md` → *Deploying on AWS*.

## Rebranding
Everything visual is in **`branding.py`** (palette, logo path, names) plus
`.streamlit/config.toml` (base theme). Change the hex values / swap `assets/logo.svg` and the
whole app follows. No colors are hardcoded elsewhere.

## Maintenance map (where to change what)
| Want to change… | File |
|---|---|
| How a LinkedIn export is parsed | `parsing/linkedin.py` |
| How a GA4 export is parsed | `parsing/ga4_csv.py` |
| Live GA4 queries / metrics pulled | `connectors/ga4.py` |
| A computed metric or delta | `analysis/*.py` |
| A takeaway or recommendation rule | `analysis/findings.py`, `narrative/engine.py` |
| A chart's look | `charts.py` |
| Colors / logo | `branding.py`, `.streamlit/config.toml` |
| A page's layout | `views/*.py` |
| Navigation / routing | `app.py` |

## Gotchas
- **Keep it out of iCloud.** The Desktop/Documents folders are iCloud-synced, which evicts
  Python package files to the cloud and makes imports hang / files vanish. This project lives
  in `~/cpai-marketing-dashboard` for that reason. Don't move it into Desktop/Documents.
- **LinkedIn exports are legacy binary `.xls`** — the parser handles both `.xls` and `.xlsx`.
- **~30-day windows:** period-over-period uses a recent-half-vs-prior-half split of the loaded
  window, clearly labelled. Longer exports enable true quarter-over-quarter comparisons.
- **GA4 not connected** → the LinkedIn→website cross-channel link can't be measured; the app
  says so and falls back to the LinkedIn-internal signal. Connect GA4 to unlock it.

## Data integrity
- Public/first-party data only; the app never invents numbers.
- The written analysis (AI or rule-based) is constrained to the figures the code computed, and
  those figures are shown alongside (see *Recommendations → Numbers behind the analysis*).
