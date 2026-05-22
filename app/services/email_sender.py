from __future__ import annotations

from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import EmailDraft, Message, now_utc
from app.services.compliance import assert_draft_sendable, normalize_email
from app.services.smartlead import add_lead_to_campaign


def _mark_message(
    db: Session,
    *,
    draft: EmailDraft,
    settings: Settings,
    provider: str,
    provider_message_id: str | None,
    status: str,
    error: str | None = None,
    provider_lead_id: str | None = None,
    provider_campaign_id: str | None = None,
    provider_payload: dict | None = None,
) -> Message:
    message = Message(
        draft=draft,
        to_email=normalize_email(draft.contact.email),
        from_email=settings.outreach_from_email,
        provider=provider,
        provider_message_id=provider_message_id,
        provider_lead_id=provider_lead_id,
        provider_campaign_id=provider_campaign_id,
        provider_payload=provider_payload or {},
        status=status,
        sent_at=now_utc() if status in {"sandbox_queued", "sent", "provider_queued", "queued_in_smartlead"} else None,
        last_event_at=now_utc(),
        error=error,
    )
    db.add(message)
    draft.status = "queued" if status == "queued_in_smartlead" else "sent" if status in {"sandbox_queued", "sent", "provider_queued"} else draft.status
    return message


async def send_draft(db: Session, *, draft: EmailDraft, settings: Settings, sandbox: bool) -> Message:
    assert_draft_sendable(db, draft=draft, settings=settings, sandbox=sandbox)
    if sandbox:
        return _mark_message(
            db,
            draft=draft,
            settings=settings,
            provider="sandbox",
            provider_message_id=f"sandbox_{uuid4()}",
            status="sandbox_queued",
        )

    if settings.sending_provider == "resend":
        payload = {
            "from": settings.outreach_from_email,
            "to": [draft.contact.email],
            "reply_to": [settings.outreach_reply_to],
            "subject": draft.subject,
            "text": f"{draft.body}\n\n{draft.compliance_footer}",
        }
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
        if response.status_code >= 400:
            return _mark_message(
                db,
                draft=draft,
                settings=settings,
                provider="resend",
                provider_message_id=None,
                status="failed",
                error=response.text[:1000],
            )
        data = response.json()
        return _mark_message(
            db,
            draft=draft,
            settings=settings,
            provider="resend",
            provider_message_id=data.get("id"),
            status="provider_queued",
        )

    if settings.sending_provider == "smartlead":
        provider_lead_id, data = await add_lead_to_campaign(settings, draft=draft)
        return _mark_message(
            db,
            draft=draft,
            settings=settings,
            provider="smartlead",
            provider_message_id=None,
            provider_lead_id=provider_lead_id,
            provider_campaign_id=settings.smartlead_campaign_id,
            provider_payload={"status": data.get("status"), "message": data.get("message")},
            status="queued_in_smartlead",
        )

    raise ValueError(f"Unsupported sending provider: {settings.sending_provider}")
