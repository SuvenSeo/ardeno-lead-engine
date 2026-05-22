from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Company, Contact, EmailDraft, LeadScore, ResearchRun, now_utc
from app.schemas import CompanyInput, ContactInput, ResearchRunCreate
from app.services.drafting import generate_ai_or_template_draft, select_contact
from app.services.scoring import score_company
from app.services.sources.clearout import ClearoutNotConfigured, verify_email
from app.services.sources.google_places import GOOGLE_PLACES_FIELD_MASK, GooglePlacesNotConfigured, text_search
from app.services.sources.hunter import HunterNotConfigured, domain_search
from app.services.sources.manual import upsert_company_from_input
from app.services.sources.website import enrich_company_website


@dataclass(frozen=True)
class ResearchProfile:
    key: str
    label: str
    terms: tuple[str, ...]
    locations: tuple[str, ...]


RESEARCH_PROFILES: dict[str, ResearchProfile] = {
    "clinics": ResearchProfile("clinics", "Clinics", ("dental clinic", "medical clinic", "doctor clinic"), ("Colombo", "Kandy", "Galle")),
    "hospitality": ResearchProfile("hospitality", "Hospitality", ("boutique hotel", "restaurant", "villa resort"), ("Colombo", "Galle", "Negombo")),
    "real_estate": ResearchProfile("real_estate", "Real estate", ("real estate agency", "property developer", "land sale"), ("Colombo", "Kandy", "Gampaha")),
    "education": ResearchProfile("education", "Education", ("academy", "private institute", "training center"), ("Colombo", "Kandy", "Kurunegala")),
    "fitness": ResearchProfile("fitness", "Fitness", ("gym", "fitness center", "yoga studio"), ("Colombo", "Kandy", "Galle")),
    "logistics": ResearchProfile("logistics", "Logistics", ("logistics company", "courier service", "transport company"), ("Colombo", "Katunayake", "Wattala")),
    "vehicle_dealers": ResearchProfile("vehicle_dealers", "Vehicle dealers", ("car dealer", "vehicle dealer", "auto sales"), ("Colombo", "Kandy", "Kurunegala")),
    "trading": ResearchProfile("trading", "Trading", ("import export company", "trading company", "wholesale distributor"), ("Colombo", "Pettah", "Wattala")),
    "professional_services": ResearchProfile("professional_services", "Professional services", ("law firm", "accounting firm", "consulting company"), ("Colombo", "Kandy", "Galle")),
}


def list_profiles() -> list[dict]:
    return [
        {"key": profile.key, "label": profile.label, "terms": list(profile.terms), "locations": list(profile.locations)}
        for profile in RESEARCH_PROFILES.values()
    ]


def generate_queries(profile_key: str, location: str) -> list[str]:
    profile = RESEARCH_PROFILES.get(profile_key)
    if not profile:
        raise ValueError(f"Unknown research profile: {profile_key}")
    locations = [location] if location and location.lower() != "sri lanka" else profile.locations
    queries = []
    for term in profile.terms:
        for city in locations:
            queries.append(f"{term} {city} Sri Lanka")
    return queries


def company_from_place(place: dict, *, profile_key: str, query: str) -> CompanyInput | None:
    name = place.get("displayName", {}).get("text")
    if not name:
        return None
    return CompanyInput(
        name=name,
        place_id=place.get("id"),
        website_url=place.get("websiteUri"),
        country="Sri Lanka",
        city=None,
        industry=", ".join(place.get("types") or [])[:160] or profile_key,
        source_trust=0.78,
        source_url="Google Places API",
        digital_footprint={
            "formatted_address": place.get("formattedAddress"),
            "business_status": place.get("businessStatus"),
            "google_rating": place.get("rating"),
            "google_user_rating_count": place.get("userRatingCount"),
            "google_query": query,
            "google_field_mask": GOOGLE_PLACES_FIELD_MASK,
            "research_profile": profile_key,
        },
    )


def has_useful_business_contact(company: Company) -> bool:
    return any(
        contact.email_type == "generic" and contact.email_status not in {"invalid", "risky"}
        for contact in company.contacts
    )


async def enrich_with_hunter(db: Session, settings: Settings, company: Company) -> int:
    if not company.domain or has_useful_business_contact(company):
        return 0
    try:
        contacts = await domain_search(settings, domain=company.domain, limit=5)
    except (HunterNotConfigured, Exception):
        return 0
    created = 0
    for item in contacts:
        existing = db.scalar(select(Contact).where(Contact.company_id == company.id, Contact.email == item["email"]).limit(1))
        if existing:
            continue
        db.add(Contact(company=company, **item))
        created += 1
    return created


async def verify_contacts(db: Session, settings: Settings, company: Company) -> int:
    updated = 0
    for contact in list(company.contacts):
        if contact.email_status in {"deliverable", "invalid", "risky"}:
            continue
        try:
            status, payload = await verify_email(settings, email=contact.email)
        except (ClearoutNotConfigured, Exception):
            continue
        contact.email_status = status
        contact.consent_notes = f"Clearout status: {status}; confidence payload stored in source observation metadata."
        updated += 1
    return updated


def latest_score(db: Session, company: Company) -> LeadScore | None:
    return db.scalar(
        select(LeadScore)
        .where(LeadScore.company_id == company.id)
        .order_by(LeadScore.created_at.desc())
        .limit(1)
    )


def has_open_draft(db: Session, company: Company) -> bool:
    return bool(
        db.scalar(
            select(EmailDraft)
            .where(EmailDraft.company_id == company.id, EmailDraft.status.in_(["draft", "approved", "queued", "sent"]))
            .limit(1)
        )
    )


async def run_research(db: Session, settings: Settings, payload: ResearchRunCreate, *, actor: str = "system") -> ResearchRun:
    threshold = payload.score_threshold if payload.score_threshold is not None else settings.auto_research_score_threshold
    max_companies = payload.max_companies or settings.auto_research_max_companies_per_run
    max_drafts = payload.max_drafts if payload.max_drafts is not None else settings.auto_research_max_drafts_per_run
    run = ResearchRun(
        profile_key=payload.profile_key,
        location=payload.location,
        status="running",
        score_threshold=threshold,
        source_summary={"queries": [], "provider_errors": []},
    )
    db.add(run)
    db.flush()

    try:
        queries = generate_queries(payload.profile_key, payload.location)
        seen = 0
        created = 0
        enriched = 0
        drafted = 0
        provider_errors: list[str] = []

        for query in queries:
            if seen >= max_companies:
                break
            run.source_summary["queries"].append(query)
            try:
                places = await text_search(settings, query=query, limit=settings.google_places_page_size)
            except GooglePlacesNotConfigured as exc:
                provider_errors.append(str(exc))
                break
            except Exception as exc:
                provider_errors.append(f"Google Places failed for {query}: {exc}")
                continue

            for place in places:
                if seen >= max_companies:
                    break
                item = company_from_place(place, profile_key=payload.profile_key, query=query)
                if not item:
                    continue
                company, was_created = upsert_company_from_input(db, payload=item, source_key="google_places")
                company.research_profile = payload.profile_key
                company.last_researched_at = now_utc()
                db.flush()
                seen += 1
                created += 1 if was_created else 0

                if company.website_url:
                    website_run = await enrich_company_website(db, company=company)
                    if website_run.status == "completed":
                        enriched += 1
                await enrich_with_hunter(db, settings, company)
                await verify_contacts(db, settings, company)
                score_company(db, company)
                db.flush()

                score = latest_score(db, company)
                if (
                    payload.create_drafts
                    and drafted < max_drafts
                    and score
                    and score.total_score >= threshold
                    and select_contact(company) is not None
                    and not has_open_draft(db, company)
                ):
                    await generate_ai_or_template_draft(db, company=company, settings=settings, use_ai=True)
                    drafted += 1
                    db.flush()

        run.status = "failed" if seen == 0 and provider_errors else "completed"
        run.companies_seen = seen
        run.companies_created = created
        run.companies_enriched = enriched
        run.drafts_created = drafted
        run.source_summary = {**run.source_summary, "provider_errors": provider_errors, "actor": actor}
        if run.status == "failed":
            run.error = "; ".join(provider_errors)[:1000] or "Research completed with no discoverable companies."
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
    finally:
        run.finished_at = now_utc()
    return run
