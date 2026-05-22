from __future__ import annotations

import re
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Campaign, Company, Contact, EmailDraft, LeadScore
from app.services.ai_drafting import OpenAIDraftNotConfigured, build_prompt_input, generate_structured_draft
from app.services.compliance import make_compliance_footer
from app.services.scoring import detect_playbook


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def latest_score(db: Session, company_id: str) -> LeadScore | None:
    return db.scalar(
        select(LeadScore)
        .where(LeadScore.company_id == company_id)
        .order_by(LeadScore.created_at.desc())
        .limit(1)
    )


def select_contact(company: Company, contact_id: str | None = None) -> Contact | None:
    contacts = list(company.contacts)
    if contact_id:
        return next((contact for contact in contacts if contact.id == contact_id), None)
    generic = [contact for contact in contacts if contact.email_type == "generic"]
    verified = [contact for contact in generic if contact.email_status in {"verified", "deliverable"}]
    if verified:
        return verified[0]
    if generic:
        return generic[0]
    return contacts[0] if contacts else None


def concrete_reason_for(company: Company, score: LeadScore | None) -> str:
    reasons = list(score.reasons if score else [])
    priority = [
        "No website recorded",
        "Missing booking/contact conversion flow",
        "Missing contact flow",
        "Weak mobile UX signal",
        "Portal/data-product fit",
        "Low digital completeness",
    ]
    for item in priority:
        if item in reasons:
            return item
    if company.industry:
        return f"your {company.industry} business looks like a fit for a sharper web flow"
    return "your public business profile looks like a fit for a sharper web flow"


def generate_draft(
    db: Session,
    *,
    company: Company,
    settings: Settings,
    campaign_id: str | None = None,
    contact_id: str | None = None,
) -> EmailDraft:
    contact = select_contact(company, contact_id)
    if not contact:
        raise ValueError("Cannot draft outreach without a contact email.")
    campaign = db.get(Campaign, campaign_id) if campaign_id else db.scalar(select(Campaign).where(Campaign.status == "active").limit(1))
    score = latest_score(db, company.id)
    reason = concrete_reason_for(company, score)
    _playbook, proof_angle = detect_playbook(company)

    greeting = f"Hi {company.name} team,"
    body = (
        f"{greeting}\n\n"
        f"I found {company.name} while reviewing businesses that may need better digital conversion. "
        f"One concrete reason: {reason.lower()}. "
        f"Ardeno Studio builds premium custom sites, portals, and data platforms; our strongest angle here is {proof_angle}.\n\n"
        f"Open to a quick look at what we would improve?"
    )
    count = word_count(body)
    if count > 100:
        body = (
            f"{greeting}\n\n"
            f"I found {company.name} while reviewing businesses with visible digital gaps. "
            f"Reason: {reason.lower()}. Ardeno Studio builds premium sites, portals, and data platforms; "
            f"the relevant proof angle is {proof_angle}.\n\n"
            f"Open to a quick look at what we would improve?"
        )
        count = word_count(body)
    if count > 100:
        raise ValueError("Draft generator produced more than 100 words.")

    draft = EmailDraft(
        company=company,
        contact=contact,
        campaign=campaign,
        subject=f"Idea for {company.name}",
        body=body,
        word_count=count,
        concrete_reason=reason,
        proof_angle=proof_angle,
        source_reason=reason,
        risk_flags=[],
        prompt_input={},
        ai_metadata={"provider": "template"},
        compliance_footer=make_compliance_footer(settings, contact.email),
        status="draft",
    )
    db.add(draft)
    return draft


async def generate_ai_or_template_draft(
    db: Session,
    *,
    company: Company,
    settings: Settings,
    campaign_id: str | None = None,
    contact_id: str | None = None,
    use_ai: bool = True,
) -> EmailDraft:
    contact = select_contact(company, contact_id)
    if not contact:
        raise ValueError("Cannot draft outreach without a contact email.")

    if not use_ai:
        return generate_draft(
            db,
            company=company,
            settings=settings,
            campaign_id=campaign_id,
            contact_id=contact.id,
        )

    score = latest_score(db, company.id)
    prompt_input = build_prompt_input(company, contact, score)
    try:
        ai_draft, metadata = await generate_structured_draft(settings, prompt_input=prompt_input)
    except (OpenAIDraftNotConfigured, httpx.HTTPError, ValueError, json.JSONDecodeError, KeyError):
        return generate_draft(
            db,
            company=company,
            settings=settings,
            campaign_id=campaign_id,
            contact_id=contact.id,
        )

    body = ai_draft["body"].strip()
    count = word_count(body)
    if count > 100:
        return generate_draft(
            db,
            company=company,
            settings=settings,
            campaign_id=campaign_id,
            contact_id=contact.id,
        )
    if re.search(r"\b(as discussed|following up|great meeting|as promised)\b", body, re.IGNORECASE):
        return generate_draft(
            db,
            company=company,
            settings=settings,
            campaign_id=campaign_id,
            contact_id=contact.id,
        )

    campaign = db.get(Campaign, campaign_id) if campaign_id else db.scalar(select(Campaign).where(Campaign.status == "active").limit(1))
    draft = EmailDraft(
        company=company,
        contact=contact,
        campaign=campaign,
        subject=ai_draft["subject"].strip()[:180],
        body=body,
        word_count=count,
        concrete_reason=ai_draft["reason"].strip(),
        proof_angle=ai_draft["proof_angle"].strip(),
        source_reason=ai_draft["source_reason"].strip(),
        risk_flags=ai_draft.get("risk_flags") or [],
        prompt_input=prompt_input,
        ai_metadata=metadata,
        compliance_footer=make_compliance_footer(settings, contact.email),
        status="draft",
    )
    db.add(draft)
    return draft
