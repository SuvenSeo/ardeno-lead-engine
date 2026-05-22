from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Contact, LeadSource, SourceObservation
from app.schemas import CompanyInput
from app.services.compliance import domain_from_url, normalize_email


def _normalized_url(url: object | None) -> str | None:
    if not url:
        return None
    return str(url).strip()


def upsert_company_from_input(db: Session, *, payload: CompanyInput, source_key: str) -> tuple[Company, bool]:
    website_url = _normalized_url(payload.website_url)
    domain = payload.domain or domain_from_url(website_url)
    existing = None
    if website_url:
        existing = db.scalar(select(Company).where(Company.website_url == website_url).limit(1))
    if not existing and domain:
        existing = db.scalar(select(Company).where(Company.domain == domain).limit(1))
    if not existing:
        existing = db.scalar(
            select(Company)
            .where(Company.name == payload.name, Company.website_url.is_(None))
            .limit(1)
        )

    created = existing is None
    company = existing or Company(name=payload.name)
    company.name = payload.name
    company.domain = domain
    company.website_url = website_url
    company.country = payload.country
    company.region = payload.region
    company.city = payload.city
    company.industry = payload.industry
    company.source_trust = payload.source_trust
    company.digital_footprint = {**(company.digital_footprint or {}), **payload.digital_footprint}
    if created:
        db.add(company)
        db.flush()

    source = db.scalar(select(LeadSource).where(LeadSource.key == source_key).limit(1))
    db.add(
        SourceObservation(
            company=company,
            source=source,
            url=payload.source_url or website_url,
            raw_payload=payload.model_dump(mode="json"),
            signals=payload.digital_footprint,
        )
    )

    for contact_payload in payload.contacts:
        email = normalize_email(str(contact_payload.email))
        contact = db.scalar(
            select(Contact).where(Contact.company_id == company.id, Contact.email == email).limit(1)
        )
        if not contact:
            contact = Contact(company=company, email=email)
            db.add(contact)
        contact.full_name = contact_payload.full_name
        contact.role = contact_payload.role
        contact.email_type = contact_payload.email_type
        contact.email_status = contact_payload.email_status
        contact.source = contact_payload.source
        contact.source_url = contact_payload.source_url or payload.source_url or website_url
        contact.processing_basis = contact_payload.processing_basis
        contact.consent_notes = contact_payload.consent_notes

    return company, created
