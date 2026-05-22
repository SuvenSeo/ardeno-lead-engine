from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    Company,
    Contact,
    DiscoveryRun,
    EmailDraft,
    LeadScore,
    Message,
    SendApproval,
    SuppressionEntry,
    now_utc,
)
from app.schemas import (
    ApprovalCreate,
    BounceWebhook,
    CompanyInput,
    DiscoveryRunCreate,
    DraftCreate,
    LeadSummary,
    MessageResponse,
    SendCreate,
    SuppressionCreate,
)
from app.security import require_admin
from app.services.audit import audit_event
from app.services.compliance import ComplianceError, add_suppression, normalize_email
from app.services.drafting import generate_draft
from app.services.email_sender import send_draft
from app.services.scoring import score_company
from app.services.seed import seed_defaults
from app.services.sources.google_places import GooglePlacesNotConfigured, text_search
from app.services.sources.manual import upsert_company_from_input
from app.services.sources.website import enrich_company_website

router = APIRouter()


def require_company(db: Session, company_id: str) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def require_draft(db: Session, draft_id: str) -> EmailDraft:
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft


def lead_summary(db: Session, company: Company) -> LeadSummary:
    score = db.scalar(
        select(LeadScore)
        .where(LeadScore.company_id == company.id)
        .order_by(LeadScore.created_at.desc())
        .limit(1)
    )
    latest_draft = db.scalar(
        select(EmailDraft)
        .where(EmailDraft.company_id == company.id)
        .order_by(EmailDraft.created_at.desc())
        .limit(1)
    )
    return LeadSummary(
        id=company.id,
        name=company.name,
        website_url=company.website_url,
        country=company.country,
        city=company.city,
        industry=company.industry,
        status=company.status,
        total_score=score.total_score if score else None,
        score_reasons=score.reasons if score else [],
        contact_count=len(company.contacts),
        latest_draft_status=latest_draft.status if latest_draft else None,
    )


async def companies_from_google(settings: Settings, payload: DiscoveryRunCreate) -> list[CompanyInput]:
    places = await text_search(settings, query=payload.query, location=payload.location)
    companies: list[CompanyInput] = []
    for place in places:
        display_name = place.get("displayName", {}).get("text")
        if not display_name:
            continue
        companies.append(
            CompanyInput(
                name=display_name,
                website_url=place.get("websiteUri"),
                country="Sri Lanka" if payload.location and "sri" in payload.location.lower() else None,
                industry=", ".join(place.get("types") or [])[:160] or None,
                source_trust=0.78,
                source_url="Google Places API",
                digital_footprint={
                    "formatted_address": place.get("formattedAddress"),
                    "business_status": place.get("businessStatus"),
                },
            )
        )
    return companies


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ardeno-leads"}


@router.post("/api/v1/discovery/runs")
async def create_discovery_run(
    payload: DiscoveryRunCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: str = Depends(require_admin),
) -> dict:
    seed_defaults(db)
    run = DiscoveryRun(source_key=payload.source_key, query=payload.query, location=payload.location, status="running")
    db.add(run)
    db.flush()

    try:
        if payload.source_key == "manual":
            company_inputs = payload.manual_companies
        elif payload.source_key == "google_places":
            company_inputs = await companies_from_google(settings, payload)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported source_key: {payload.source_key}")

        if not company_inputs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No companies supplied or discovered.")

        created = 0
        summaries: list[LeadSummary] = []
        for item in company_inputs:
            company, was_created = upsert_company_from_input(db, payload=item, source_key=payload.source_key)
            created += 1 if was_created else 0
            score_company(db, company)
            db.flush()
            summaries.append(lead_summary(db, company))

        run.status = "completed"
        run.companies_created = created
        run.companies_seen = len(company_inputs)
        run.finished_at = now_utc()
        audit_event(db, actor=actor, action="discovery.completed", entity_type="discovery_run", entity_id=run.id, metadata={"source_key": payload.source_key})
        db.commit()
        return {"id": run.id, "status": run.status, "companies_created": created, "companies_seen": len(company_inputs), "leads": [item.model_dump() for item in summaries]}
    except GooglePlacesNotConfigured as exc:
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = now_utc()
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        run.status = "failed"
        run.finished_at = now_utc()
        db.commit()
        raise


@router.get("/api/v1/leads", response_model=list[LeadSummary])
def list_leads(
    db: Session = Depends(get_db),
    _actor: str = Depends(require_admin),
) -> list[LeadSummary]:
    companies = db.scalars(select(Company).order_by(Company.updated_at.desc(), Company.created_at.desc()).limit(200)).all()
    return [lead_summary(db, company) for company in companies]


@router.get("/api/v1/leads/{company_id}")
def get_lead(
    company_id: str,
    db: Session = Depends(get_db),
    _actor: str = Depends(require_admin),
) -> dict:
    company = require_company(db, company_id)
    return {
        "lead": lead_summary(db, company).model_dump(),
        "company": {
            "id": company.id,
            "name": company.name,
            "domain": company.domain,
            "website_url": company.website_url,
            "country": company.country,
            "region": company.region,
            "city": company.city,
            "industry": company.industry,
            "digital_footprint": company.digital_footprint,
        },
        "contacts": [
            {
                "id": contact.id,
                "full_name": contact.full_name,
                "role": contact.role,
                "email": contact.email,
                "email_type": contact.email_type,
                "email_status": contact.email_status,
                "source": contact.source,
                "source_url": contact.source_url,
                "processing_basis": contact.processing_basis,
            }
            for contact in company.contacts
        ],
    }


@router.post("/api/v1/leads/{company_id}/enrich")
async def enrich_lead(
    company_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    company = require_company(db, company_id)
    run = await enrich_company_website(db, company=company)
    if run.status == "completed":
        score_company(db, company)
    audit_event(db, actor=actor, action="lead.enriched", entity_type="company", entity_id=company.id, metadata={"status": run.status, "source": run.source})
    db.commit()
    return {"id": run.id, "status": run.status, "summary": run.summary, "error": run.error, "lead": lead_summary(db, company).model_dump()}


@router.post("/api/v1/leads/{company_id}/drafts")
def create_draft(
    company_id: str,
    payload: DraftCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: str = Depends(require_admin),
) -> dict:
    company = require_company(db, company_id)
    try:
        draft = generate_draft(db, company=company, settings=settings, campaign_id=payload.campaign_id, contact_id=payload.contact_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_event(db, actor=actor, action="draft.created", entity_type="email_draft", entity_id=draft.id, metadata={"company_id": company.id})
    db.commit()
    db.refresh(draft)
    return serialize_draft(draft)


@router.get("/api/v1/drafts")
def list_drafts(
    company_id: str | None = None,
    db: Session = Depends(get_db),
    _actor: str = Depends(require_admin),
) -> list[dict]:
    query = select(EmailDraft).order_by(EmailDraft.created_at.desc()).limit(100)
    if company_id:
        query = select(EmailDraft).where(EmailDraft.company_id == company_id).order_by(EmailDraft.created_at.desc()).limit(100)
    return [serialize_draft(draft) for draft in db.scalars(query).all()]


@router.post("/api/v1/drafts/{draft_id}/approval")
def decide_draft(
    draft_id: str,
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    draft = require_draft(db, draft_id)
    if draft.status == "sent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sent drafts cannot be changed.")
    approval = SendApproval(
        draft=draft,
        approver_email=normalize_email(str(payload.approver_email)),
        decision=payload.decision,
        notes=payload.notes,
    )
    db.add(approval)
    draft.status = payload.decision
    audit_event(db, actor=actor, action=f"draft.{payload.decision}", entity_type="email_draft", entity_id=draft.id, metadata={"approver_email": approval.approver_email})
    db.commit()
    db.refresh(draft)
    return serialize_draft(draft)


@router.post("/api/v1/drafts/{draft_id}/send", response_model=MessageResponse)
async def send_approved_draft(
    draft_id: str,
    payload: SendCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: str = Depends(require_admin),
) -> MessageResponse:
    draft = require_draft(db, draft_id)
    try:
        message = await send_draft(db, draft=draft, settings=settings, sandbox=payload.sandbox)
    except ComplianceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_event(db, actor=actor, action="message.send_requested", entity_type="message", entity_id=message.id, metadata={"sandbox": payload.sandbox, "draft_id": draft.id})
    db.commit()
    db.refresh(message)
    return MessageResponse(id=message.id, status=message.status, provider=message.provider, to_email=message.to_email, from_email=message.from_email)


@router.post("/api/v1/suppressions")
def create_suppression(
    payload: SuppressionCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    entry = add_suppression(db, value=payload.value, value_type=payload.value_type, reason=payload.reason, source=payload.source)
    audit_event(db, actor=actor, action="suppression.created", entity_type="suppression", entity_id=entry.id, metadata={"value_type": payload.value_type})
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "value": entry.value, "value_type": entry.value_type, "reason": entry.reason}


@router.get("/api/v1/metrics")
def metrics(
    db: Session = Depends(get_db),
    _actor: str = Depends(require_admin),
) -> dict:
    draft_statuses = dict(db.execute(select(EmailDraft.status, func.count(EmailDraft.id)).group_by(EmailDraft.status)).all())
    message_statuses = dict(db.execute(select(Message.status, func.count(Message.id)).group_by(Message.status)).all())
    return {
        "companies": db.scalar(select(func.count(Company.id))) or 0,
        "contacts": db.scalar(select(func.count(Contact.id))) or 0,
        "suppressed": db.scalar(select(func.count(SuppressionEntry.id))) or 0,
        "drafts": draft_statuses,
        "messages": message_statuses,
        "approved_drafts": draft_statuses.get("approved", 0),
        "sent_or_queued": sum(message_statuses.get(key, 0) for key in ["sandbox_queued", "sent", "provider_queued"]),
        "bounces": sum(message_statuses.get(key, 0) for key in ["bounced", "complained"]),
    }


@router.get("/api/v1/unsubscribe")
def unsubscribe(
    email: str = Query(min_length=3),
    db: Session = Depends(get_db),
) -> dict:
    entry = add_suppression(db, value=email, value_type="email", reason="unsubscribe", source="unsubscribe_link")
    audit_event(db, actor="recipient", action="unsubscribe", entity_type="suppression", entity_id=entry.id, metadata={"email": normalize_email(email)})
    db.commit()
    return {"status": "suppressed", "email": normalize_email(email)}


@router.post("/api/v1/webhooks/bounce")
def bounce_webhook(
    payload: BounceWebhook,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    message = None
    if payload.message_id:
        message = db.get(Message, payload.message_id)
    if not message and payload.provider_message_id:
        message = db.scalar(select(Message).where(Message.provider_message_id == payload.provider_message_id).limit(1))
    if message:
        message.status = "complained" if payload.event == "complaint" else "bounced"
        message.last_event_at = now_utc()
        message.error = payload.reason
        email = message.to_email
    elif payload.email:
        email = normalize_email(str(payload.email))
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message_id, provider_message_id, or email is required.")

    entry = add_suppression(db, value=email, value_type="email", reason=payload.event, source="webhook")
    audit_event(db, actor=actor, action=f"message.{payload.event}", entity_type="message", entity_id=message.id if message else None, metadata={"email": email})
    db.commit()
    return {"status": "recorded", "suppression_id": entry.id}


def serialize_draft(draft: EmailDraft) -> dict:
    return {
        "id": draft.id,
        "company_id": draft.company_id,
        "contact_id": draft.contact_id,
        "campaign_id": draft.campaign_id,
        "subject": draft.subject,
        "body": draft.body,
        "word_count": draft.word_count,
        "concrete_reason": draft.concrete_reason,
        "proof_angle": draft.proof_angle,
        "compliance_footer": draft.compliance_footer,
        "status": draft.status,
    }
