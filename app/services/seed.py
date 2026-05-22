from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, LeadSource


DEFAULT_SOURCES = [
    {
        "key": "manual",
        "name": "Manual import",
        "kind": "approved_import",
        "trust_score": 0.75,
        "terms_url": None,
        "allowed_use_notes": "Operator-approved CSV or manual entry with source URL retained.",
    },
    {
        "key": "google_places",
        "name": "Google Places API",
        "kind": "api",
        "trust_score": 0.78,
        "terms_url": "https://developers.google.com/maps/terms",
        "allowed_use_notes": "Use official API and field masks only; do not scrape Google surfaces.",
    },
    {
        "key": "company_website",
        "name": "Company website",
        "kind": "first_party_public",
        "trust_score": 0.82,
        "terms_url": None,
        "allowed_use_notes": "Fetch public business website/contact pages only for enrichment.",
    },
    {
        "key": "imported_directory",
        "name": "Approved public directory import",
        "kind": "approved_import",
        "trust_score": 0.62,
        "terms_url": None,
        "allowed_use_notes": "Only import directories whose terms allow business outreach use.",
    },
    {
        "key": "apollo",
        "name": "Apollo enrichment",
        "kind": "api",
        "trust_score": 0.72,
        "terms_url": "https://docs.apollo.io/docs/enrich-people-data",
        "allowed_use_notes": "Use API terms and store provider provenance for contacts.",
    },
    {
        "key": "hunter",
        "name": "Hunter enrichment",
        "kind": "api",
        "trust_score": 0.7,
        "terms_url": "https://hunter.io/api",
        "allowed_use_notes": "Use API terms and prefer generic business inboxes.",
    },
    {
        "key": "clearout",
        "name": "Clearout verification",
        "kind": "api",
        "trust_score": 0.7,
        "terms_url": "https://docs.clearout.io/email-verifier-api.html",
        "allowed_use_notes": "Use for email verification before production sending.",
    },
    {
        "key": "openai",
        "name": "OpenAI structured draft generation",
        "kind": "api",
        "trust_score": 0.68,
        "terms_url": "https://platform.openai.com/docs/guides/structured-outputs",
        "allowed_use_notes": "Use only sourced facts and schema-constrained draft outputs.",
    },
    {
        "key": "smartlead",
        "name": "Smartlead approved outreach queue",
        "kind": "api",
        "trust_score": 0.72,
        "terms_url": "https://api.smartlead.ai/",
        "allowed_use_notes": "Queue only human-approved drafts and sync suppressions/webhooks.",
    },
]


def seed_defaults(db: Session) -> None:
    for row in DEFAULT_SOURCES:
        existing = db.scalar(select(LeadSource).where(LeadSource.key == row["key"]))
        if existing:
            for key, value in row.items():
                setattr(existing, key, value)
        else:
            db.add(LeadSource(**row))

    if not db.scalar(select(Campaign).where(Campaign.name == "V1 human-approved outreach")):
        db.add(
            Campaign(
                name="V1 human-approved outreach",
                icp_key="multi_icp_smb",
                status="active",
                daily_cap=20,
            )
        )
