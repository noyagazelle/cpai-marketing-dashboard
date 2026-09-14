# CyberPro AI — Marketing Analytics Dashboard

An internal, web-based dashboard that turns **LinkedIn company-page exports** and
**Google Analytics 4 (GA4)** data into clear KPIs, visual analysis, and concrete
recommendations for leadership.

- Drop in your LinkedIn `.xls`/`.xlsx` exports — types are auto-detected.
- Connect GA4 live (service account) **or** upload a manual CSV/Excel export.
- Every number is **computed deterministically** from your data; nothing is invented.

---

## ⚠️ Important: where this project lives

This app is installed at **`~/cpai-marketing-dashboard`** (i.e.
`/Users/<you>/cpai-marketing-dashboard`) — deliberately **outside** your iCloud-synced
`Desktop`/`Documents` folders. iCloud "optimises" storage by evicting files to the cloud,
which breaks a Python environment (imports hang, files disappear). **Keep the project and
its `.venv` outside iCloud.**

---

## Quick start

```bash
cd ~/cpai-marketing-dashboard

# one-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# run it
.venv/bin/streamlit run app.py
```

Your browser opens at **`http://localhost:8501`** — this link never changes, so you can keep
the tab open and just refresh it. To stop the app, press `Ctrl+C` in the terminal.

---

## Using it

Everything starts on the **Upload & connect** tab (the landing page):

1. **LinkedIn exports.** From your LinkedIn Company Page → **Analytics**, export **Visitors**,
   **Followers**, and **Content/Updates** (and **Competitors** if available). Drag the files
   onto the LinkedIn drop-zone — types are auto-detected and any subset works. The dashboard
   ships with June 2026 sample data so it's never empty; your upload replaces it.
2. **Website (GA4).** Connect live (see setup below) or upload a manual CSV/Excel export in
   the GA4 panel. When connected live, pick a date range and click **Refresh** to re-pull.

Then use the top tab bar to explore. The **Data & export** tab lets you download any
underlying table as CSV or a multi-sheet Excel workbook.

### Quarterly routine (the main workflow)

Each period, you only need to:

1. Export the three LinkedIn files for the quarter and (optionally) the GA4 report.
2. Open **Upload & connect** and drop the LinkedIn files in — the detected **period** is shown
   so you can confirm you loaded the right window.
3. Refresh GA4 (live) or upload the new GA4 export.
4. Read **Executive summary** and **Recommendations**; export tables from **Data & export** if
   you need them for a deck.

That's it — every chart, KPI, and recommendation recomputes automatically from the new files.

---

## GA4 setup (live connection) — step by step

You only do this once. It lets the dashboard pull GA4 data automatically.

### 1. Enable the Analytics Data API
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or pick an existing one) — top-left project dropdown → **New Project**.
3. Search for **"Google Analytics Data API"** → open it → click **Enable**.

### 2. Create a service account + JSON key
1. In the Cloud Console: **APIs & Services → Credentials**.
2. **Create credentials → Service account**. Give it a name (e.g. `cpai-ga4-reader`) → **Done**.
3. Open the new service account → **Keys** tab → **Add key → Create new key → JSON** →
   **Create**. A `.json` file downloads. **Move it somewhere safe and non-synced**, e.g.
   `~/keys/cpai-ga4-service-account.json`. Treat it like a password.
4. Copy the service account's **email** (looks like
   `cpai-ga4-reader@your-project.iam.gserviceaccount.com`).

### 3. Give the service account access to your GA4 property
1. In [Google Analytics](https://analytics.google.com/): **Admin** (bottom-left gear).
2. Under the **Property** column → **Property Access Management**.
3. **+ (top right) → Add users** → paste the service account email → role **Viewer** →
   uncheck "Notify by email" → **Add**.

### 4. Find your numeric Property ID
- **Admin → Property Settings** → copy the **Property ID** (a number like `123456789`).
  *(Not the "G-XXXX" measurement ID — that's different.)*

### 5. Tell the dashboard
Create a file named `.env` in the project folder (copy `.env.example`) and fill in:

```
GA4_PROPERTY_ID=123456789
GA4_SERVICE_ACCOUNT_JSON=/Users/you/keys/cpai-ga4-service-account.json
```

Restart the app. The **Website (GA4)** view should show **✓ Connected**.

---

## GA4 without a service account (manual export fallback)

No credentials? You can still use website data:

1. In GA4, open a report (e.g. **Reports → Acquisition → Traffic acquisition**, or an
   **Explore**), set your date range, and **export as CSV** (or Excel). For trend charts,
   include a **Date** dimension.
2. In the dashboard's **Website (GA4)** view, use **Upload a GA4 CSV / Excel export**.

The parser tolerates GA4's `#` comment lines and multi-table exports and maps the common
metrics automatically. Summed users from a daily export are approximate (not de-duplicated) —
the live API gives exact unique users.

---

## AI-written analysis (optional)

If you set `ANTHROPIC_API_KEY` in `.env`, the written executive analysis is generated by
Claude **over the numbers the app already computed** (it never produces figures itself). If
no key is set, a solid rule-based narrative is used. To check whether you have a key:

```bash
echo $ANTHROPIC_API_KEY        # prints nothing if unset
```

You can get a key at <https://console.anthropic.com/> → **API Keys**.

---

## Access control

No one gets in until someone is registered — see `_auth_gate()` in `app.py`. Teammates set
their **own** password; no admin ever types or sees it:

1. An admin invites an email address — either `AUTH_PRE_AUTHORIZED` in `.env` (bootstrap, before
   anyone can log in), or the **Manage access** tab once someone is already logged in.
2. That person opens the app, expands **"New here? Set up your account,"** and picks their own
   username + password.
3. Their invite is consumed and their account (bcrypt-hashed password) is added to `AUTH_USERS`
   automatically — nothing to hand-edit.

Leave `AUTH_PRE_AUTHORIZED` and `AUTH_USERS` both unset to skip the login screen entirely
(local dev, matches the behavior described throughout this README).

---

## Configuration & security

- All secrets live in `.env` (git-ignored) — never in source. `.env.example` shows the shape.
- On Streamlit Cloud, use **Secrets** instead of `.env` (same key names; a service-account
  JSON can be pasted inline as `GA4_SERVICE_ACCOUNT_INFO`).
- On the AWS deployment (see below), the same key names are passed as plain container
  environment variables instead.
- Branding (colors, logo, names) is all in `branding.py` — trivial to rebrand.

---

## Deploying on AWS (current production setup)

This app runs as a container on **AWS Lightsail** (chosen for cost/simplicity over ECS/App
Runner — see project notes). No VPC, load balancer, or ECS cluster involved.

### What's running
- **Lightsail container service**: `marketing-dashboard` (region `us-east-1`, `nano` power,
  ~$7/month). All resources below are tagged `project: marketing-dashboard`.
- **S3 bucket**: `marketing-dashboard-history-<account-id>` — durable storage for uploaded
  LinkedIn periods (`history.py`'s S3 backend), since the container's local disk is wiped on
  every redeploy.
- **IAM user**: `marketing-dashboard-app` — scoped to only `GetObject`/`PutObject`/
  `DeleteObject`/`ListBucket` on that one bucket. Its access key is passed to the container as
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars (Lightsail containers have no IAM role
  support, unlike ECS).

### Redeploying after a code change
```bash
docker build --platform linux/amd64 -t cpai-dashboard:latest .
aws lightsail push-container-image --service-name marketing-dashboard --label app \
  --image cpai-dashboard:latest --region us-east-1
# note the returned image tag, e.g. ":marketing-dashboard.app.3", then:
aws lightsail create-container-service-deployment --region us-east-1 --cli-input-json '{
  "serviceName": "marketing-dashboard",
  "containers": {"app": {
    "image": ":marketing-dashboard.app.3",
    "ports": {"8501": "HTTP"},
    "environment": { "...": "carry forward every existing env var here — a deployment replaces the full env, it does not merge" }
  }},
  "publicEndpoint": {"containerName": "app", "containerPort": 8501,
    "healthCheck": {"path": "/", "successCodes": "200-499"}}
}'
```
Always fetch the current env vars first (`aws lightsail get-container-services --service-name
marketing-dashboard --region us-east-1`) and carry them all forward — a deployment replaces the
entire environment, it doesn't merge with the previous one.

### A known limitation worth knowing
`AUTH_USERS`/`AUTH_PRE_AUTHORIZED` are plain env vars on the deployment, not backed by Secrets
Manager. That means invites/registrations made through **Manage access** live only in the
running container's memory — a redeploy resets them to whatever's in the deployment spec above.
For a small team this is an acceptable, low-friction trade-off (just copy the current
`AUTH_USERS` value into the next deployment's env vars if it's changed) rather than adding an
IAM-credential round-trip to Secrets Manager purely for auth state. `config.py` already supports
that upgrade path (`AUTH_SECRET_ID`) if this ever becomes worth doing.

---

## Deploying to Streamlit Community Cloud (alternative)

If you'd rather not run this on AWS, Streamlit's own hosting is simpler for local-only teams:

1. **Put the project in a Git repo** (private is fine). It's already git-initialised with a
   `.gitignore` that excludes `.env` and any key files — never commit secrets.
2. Go to <https://share.streamlit.io> → **New app** → pick the repo → main file `app.py`.
3. **Add secrets** (App → Settings → **Secrets**) instead of a `.env`. Use the same key names
   as `.env.example`, including `AUTH_PRE_AUTHORIZED`/`AUTH_USERS` for login and
   `GCS_BUCKET` (not `S3_BUCKET`) for persistent history storage on that platform.
4. Deploy. The iCloud caveat doesn't apply in the cloud.

---

## Project structure

```
cpai-marketing-dashboard/
├── app.py                  # Streamlit entry point: nav + session data flow
├── loaders.py              # LinkedIn export loaders (upload + samples)
├── branding.py             # colors, logo, fonts (rebrand here)
├── config.py               # env / .env / secrets loading; date ranges
├── charts.py               # reusable Plotly builders (on-brand)
├── ui.py                   # KPI cards, callouts, formatting helpers
├── .streamlit/config.toml  # base light theme
├── parsing/
│   ├── linkedin.py         # tolerant LinkedIn .xls/.xlsx parser
│   └── ga4_csv.py          # tolerant GA4 CSV/Excel fallback parser
├── connectors/
│   └── ga4.py              # live GA4 Data API connector
├── analysis/
│   ├── linkedin.py         # deterministic LinkedIn metrics
│   ├── ga4.py              # deterministic GA4 metrics
│   ├── cross_channel.py    # LinkedIn↔website alignment + correlations
│   ├── findings.py         # headline KPIs + prioritized takeaways
│   └── tables.py           # appendix table collection + CSV/Excel export
├── narrative/
│   └── engine.py           # recommendations + AI / rule-based written analysis
├── views/
│   ├── upload_view.py      # Upload & connect (landing page)
│   ├── executive_view.py   # executive summary
│   ├── linkedin_view.py    # LinkedIn deep dive
│   ├── ga4_view.py         # website (GA4) deep dive
│   ├── cross_channel_view.py
│   ├── audience_view.py
│   ├── recommendations_view.py
│   └── appendix_view.py    # data appendix + downloads
├── sample_data/            # bundled LinkedIn sample exports
├── requirements.txt
└── .env.example
```

The dashboard has eight views (top tab bar): **Upload & connect** (load each period's data),
**Executive summary**, **LinkedIn deep dive**, **Website (GA4)**, **Cross-channel**,
**Audience**, **Recommendations**, and **Data & export** (browse/filter every underlying table
and download it as CSV or a multi-sheet Excel workbook).

## Troubleshooting

- **GA4 says "Not connected"** — check `.env` has both `GA4_PROPERTY_ID` and
  `GA4_SERVICE_ACCOUNT_JSON`, and that you restarted the app.
- **`403 PERMISSION_DENIED` from GA4** — the service-account email isn't a **Viewer** on the
  property (step 3), or you used the wrong (measurement `G-XXXX`) ID instead of the numeric one.
- **Imports hang / files vanish** — the project is inside iCloud. Move it out (see top).
