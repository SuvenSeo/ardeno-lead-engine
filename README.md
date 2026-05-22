# Ardeno Lead Engine

Private internal service for compliance-first lead discovery, enrichment, scoring, draft approval, sandbox sending, suppression, and outreach metrics.

## What v1 Does

- Imports approved/manual leads or discovers businesses through the official Google Places API.
- Stores company, contact, source, observation, score, draft, approval, message, suppression, and audit records.
- Scores leads using multi-ICP fit, need, source trust, contact quality, and Ardeno proof angle.
- Generates deterministic outreach drafts under 100 words.
- Requires human approval before any send request.
- Defaults to sandbox sending and fails closed for production sending until sender DNS/auth is explicitly verified.
- Applies global suppression before every send.
- Exposes an internal dashboard at `/`.

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

Vercel detects the FastAPI app from `app/index.py`. Preview deployments use SQLite in `/tmp` by default so the service boots without secrets, but this storage is ephemeral. Set `ADMIN_API_KEY` in Vercel before operating the dashboard, and set `DATABASE_URL` to a managed Postgres database before real internal use.

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
- `GET /leads`
- `GET /leads/{company_id}`
- `POST /leads/{company_id}/enrich`
- `POST /leads/{company_id}/drafts`
- `GET /drafts?company_id=...`
- `POST /drafts/{draft_id}/approval`
- `POST /drafts/{draft_id}/send`
- `POST /suppressions`
- `GET /metrics`
- `GET /unsubscribe?email=...`
- `POST /webhooks/bounce`

All internal APIs require `X-Admin-Key` except health and unsubscribe.

## Notes

The v1 implementation intentionally avoids LinkedIn scraping, LinkedIn DM automation, and blind email blasting. Use official APIs or operator-approved imports only, and retain source URLs and processing basis for contacts.
