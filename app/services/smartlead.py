from __future__ import annotations

import httpx

from app.config import Settings
from app.models import EmailDraft
from app.services.compliance import normalize_email


class SmartleadNotConfigured(RuntimeError):
    pass


def build_smartlead_payload(draft: EmailDraft, settings: Settings) -> dict:
    company = draft.company
    contact = draft.contact
    return {
        "lead_list": [
            {
                "email": normalize_email(contact.email),
                "first_name": contact.full_name or company.name,
                "company_name": company.name,
                "website": company.website_url,
                "custom_fields": {
                    "ardeno_company_id": company.id,
                    "ardeno_draft_id": draft.id,
                    "ardeno_score_reason": draft.concrete_reason,
                    "ardeno_proof_angle": draft.proof_angle,
                    "ardeno_source_reason": draft.source_reason or draft.concrete_reason,
                    "ardeno_email_subject": draft.subject,
                    "ardeno_email_body": f"{draft.body}\n\n{draft.compliance_footer}",
                },
            }
        ],
        "settings": {
            "ignore_global_block_list": False,
            "ignore_unsubscribe_list": False,
        },
    }


async def add_lead_to_campaign(settings: Settings, *, draft: EmailDraft) -> tuple[str | None, dict]:
    if not settings.smartlead_api_key or not settings.smartlead_campaign_id:
        raise SmartleadNotConfigured("SMARTLEAD_API_KEY and SMARTLEAD_CAMPAIGN_ID are required.")

    payload = build_smartlead_payload(draft, settings)
    url = f"https://server.smartlead.ai/api/v1/campaigns/{settings.smartlead_campaign_id}/leads"
    params = {"api_key": settings.smartlead_api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, params=params, json=payload)
    response.raise_for_status()
    data = response.json()
    lead_id = (
        data.get("lead_id")
        or data.get("id")
        or (data.get("lead_ids") or [None])[0]
        or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("lead_id")
    )
    return str(lead_id) if lead_id else None, data


async def add_to_global_blocklist(settings: Settings, *, email: str) -> dict:
    if not settings.smartlead_api_key:
        raise SmartleadNotConfigured("SMARTLEAD_API_KEY is required.")
    params = {"api_key": settings.smartlead_api_key}
    payload = {"email": normalize_email(email)}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post("https://server.smartlead.ai/api/v1/global-block-list", params=params, json=payload)
    response.raise_for_status()
    return response.json()
