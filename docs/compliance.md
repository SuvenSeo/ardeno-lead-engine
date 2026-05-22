# Compliance Controls

This service is designed to make unsafe outbound behavior difficult by default. It is not a legal approval substitute.

## Data Provenance

Each imported or enriched contact should retain:

- source URL or provider name,
- extraction or import timestamp,
- processing basis,
- source trust score,
- audit trail entry for discovery, draft, approval, send, suppression, unsubscribe, and webhook events.

Because the GitHub repo is public, never commit real lead records, exported provider payloads, screenshots with identifiable leads, local databases, or environment files.

## Sender Rules

Every commercial email must include:

- Ardeno Studio identity,
- valid physical mailing address,
- a reason the recipient is being contacted,
- a frictionless opt-out link.

Production sending must stay disabled until sender authentication and monitoring are ready:

- Vercel `DATABASE_URL` points at managed Postgres/Neon, not SQLite,
- SPF,
- DKIM,
- DMARC,
- reply mailbox,
- unsubscribe endpoint,
- bounce and complaint handling,
- daily cap review.

Smartlead queueing still counts as outbound activity. A draft must be human-approved and pass local suppression checks before it can be added to a Smartlead campaign.

## Suppression

Suppression is global and checked before every send. Supported suppression types:

- `email`,
- `domain`,
- `company`.

Unsubscribe and bounce webhooks create email-level suppressions automatically.

## v1 Explicit Exclusions

- No LinkedIn scraping.
- No automated LinkedIn DMs.
- No fully autonomous cold email blasting.
- No production send from the primary brand domain until authentication and reputation monitoring are verified.
- No committing real lead data or secrets to the public repository.

## Scaling Criteria

Before raising volume or enabling follow-ups, validate:

- low bounce rate,
- low complaint rate,
- clean suppression handling,
- reply classification quality,
- deliverability logs,
- legal review for target jurisdictions.
