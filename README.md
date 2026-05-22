# Ardeno Lead Engine

Private internal service for compliance-first autonomous lead research, enrichment, scoring, AI-assisted draft approval, Smartlead queueing, suppression, and outreach metrics.

## What v1 Does

- Imports approved/manual leads or discovers businesses through the official Google Places API.
- Runs autonomous Sri Lanka SMB research profiles through manual API calls or Vercel Cron.
- Stores company, contact, source, observation, score, draft, approval, message, suppression, and audit records.
- Scores leads using multi-ICP fit, need, source trust, contact quality, and Ardeno proof angle.
- Generates OpenAI-assisted drafts under 100 words when configured, with deterministic fallback.
- Requires human approval before any send request.
- Queues approved non-sandbox outreach through Smartlead when configured.
- Defaults to sandbox sending and fails closed for production sending until provider, sender DNS/auth, and compliance settings are explicitly verified.
- Applies global suppression before every send.
- Exposes a dark Ardeno operations dashboard at `/`.

## Local Setup

```powershell
cd ardeno-leads
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8088
```

Open `http://127.0.0.1:8088/` and use `X-Admin-Key` from `.env`.

## Vercel Preview Deployment

Vercel detects the FastAPI app from `app/index.py`. On Vercel, lead data endpoints fail closed until `DATABASE_URL` is set to a managed Postgres database. This prevents accidental production use of ephemeral SQLite storage.

Use Neon Postgres for persistent production data:

```powershell
alembic upgrade head
```

Required Vercel env vars before real operation:

- `ADMIN_API_KEY`
- `DATABASE_URL`
- `GOOGLE_PLACES_API_KEY`
- `HUNTER_API_KEY`
- `CLEAROUT_API_KEY`
- `OPENAI_API_KEY`
- `SMARTLEAD_API_KEY`
- `SMARTLEAD_CAMPAIGN_ID`
- `CRON_SECRET`
- `OUTREACH_POSTAL_ADDRESS`
- `SENDER_DNS_AUTH_VERIFIED=true` only after sender authentication is complete

## Required Production Gates

Do not set `SENDER_DNS_AUTH_VERIFIED=true` until SPF, DKIM, DMARC, reply mailbox, unsubscribe path, monitoring, and sender reputation monitoring are confirmed for the real sending domain or subdomain.

Production sends are blocked when:

- the draft is not approved,
- the recipient or company is suppressed,
- the compliance footer is incomplete,
- the daily sender cap is reached,
- `SENDING_PROVIDER=sandbox`,
- DNS/auth has not been explicitly verified,
- the chosen provider key is missing.

## API Shape

Core endpoints live under `/api/v1`:

- `POST /discovery/runs`
- `GET /research/profiles`
- `POST /research/runs`
- `GET /research/runs`
- `GET /recommendations`
- `GET /cron/research`
- `GET /leads`
- `GET /leads/{company_id}`
- `POST /leads/{company_id}/enrich`
- `POST /leads/{company_id}/drafts`
- `GET /drafts?company_id=...`
- `POST /drafts/{draft_id}/approval`
- `POST /drafts/{draft_id}/approve-and-send`
- `POST /drafts/{draft_id}/send`
- `POST /suppressions`
- `GET /metrics`
- `GET /unsubscribe?email=...`
- `POST /webhooks/bounce`
- `POST /webhooks/smartlead`

All internal APIs require `X-Admin-Key` except health and unsubscribe.

## Notes

The v1 implementation intentionally avoids LinkedIn scraping, LinkedIn DM automation, and blind email blasting. Use official APIs or operator-approved imports only, and retain source URLs and processing basis for contacts.

This repository is public. Do not commit real leads, provider payload exports, `.env` files, screenshots with live lead data, or any API keys.
