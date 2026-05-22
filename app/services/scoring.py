from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Company, LeadScore


VERTICAL_PLAYBOOKS = {
    "hospitality": {
        "terms": ["hotel", "restaurant", "cafe", "villa", "resort", "hospitality", "travel"],
        "proof": "booking and premium site proof",
    },
    "clinics": {
        "terms": ["clinic", "doctor", "dental", "medical", "health", "care"],
        "proof": "appointment and patient inquiry flow proof",
    },
    "fitness": {
        "terms": ["gym", "fitness", "wellness", "yoga", "trainer"],
        "proof": "membership and lead-capture proof",
    },
    "real_estate": {
        "terms": ["real estate", "property", "lands", "developer"],
        "proof": "listing portal and CRM workflow proof",
    },
    "education": {
        "terms": ["school", "academy", "campus", "education", "institute", "tuition"],
        "proof": "student portal and enrollment flow proof",
    },
    "trading": {
        "terms": ["trading", "import", "export", "distributor", "wholesale"],
        "proof": "catalog and B2B inquiry proof",
    },
    "logistics": {
        "terms": ["logistics", "transport", "shipping", "courier", "freight"],
        "proof": "operations dashboard proof",
    },
    "vehicle_dealers": {
        "terms": ["vehicle", "auto", "car", "dealer", "motor"],
        "proof": "vehicle platform and price intelligence proof",
    },
    "professional_services": {
        "terms": ["law", "accounting", "consulting", "agency", "service", "studio"],
        "proof": "premium service website proof",
    },
}


def detect_playbook(company: Company) -> tuple[str, str]:
    haystack = " ".join(filter(None, [company.industry, company.name])).lower()
    for key, playbook in VERTICAL_PLAYBOOKS.items():
        if any(term in haystack for term in playbook["terms"]):
            return key, playbook["proof"]
    return "remote_smb", "premium custom website and data-platform proof"


def latest_signals(company: Company) -> dict:
    signals = dict(company.digital_footprint or {})
    for observation in sorted(company.observations, key=lambda item: item.observed_at or datetime.min, reverse=True):
        signals.update(observation.signals or {})
    return signals


def score_company(db: Session, company: Company) -> LeadScore:
    signals = latest_signals(company)
    playbook, proof_angle = detect_playbook(company)
    reasons: list[str] = [f"ICP playbook: {playbook}", f"Proof angle: {proof_angle}"]

    sri_lanka_fit = 12 if (company.country or "").lower() in {"sri lanka", "lk"} else 0
    named_industry_fit = 18 if company.industry else 8
    vertical_fit = 28 if playbook != "remote_smb" else 18
    fit_score = min(100, 38 + sri_lanka_fit + named_industry_fit + vertical_fit)

    need_score = 20
    if not company.website_url:
        need_score += 42
        reasons.append("No website recorded")
    if signals.get("weak_mobile_ux"):
        need_score += 18
        reasons.append("Weak mobile UX signal")
    if signals.get("missing_booking_flow"):
        need_score += 14
        reasons.append("Missing booking/contact conversion flow")
    if signals.get("missing_contact_flow"):
        need_score += 14
        reasons.append("Missing contact flow")
    if signals.get("slow_site"):
        need_score += 12
        reasons.append("Slow site signal")
    if signals.get("stale_pages"):
        need_score += 10
        reasons.append("Stale page signal")
    if signals.get("low_digital_completeness"):
        need_score += 12
        reasons.append("Low digital completeness")
    if signals.get("portal_or_data_fit"):
        need_score += 18
        reasons.append("Portal/data-product fit")
    need_score = min(100, need_score)

    contact_score = 0
    contacts = list(company.contacts)
    if contacts:
        contact_score += 35
        reasons.append("Contact available")
    if any(contact.email_type == "generic" for contact in contacts):
        contact_score += 25
        reasons.append("Generic business inbox preferred")
    if any(contact.email_status in {"verified", "deliverable"} for contact in contacts):
        contact_score += 25
        reasons.append("Verified email signal")
    if any(contact.processing_basis for contact in contacts):
        contact_score += 10
    contact_score = min(100, contact_score)

    proof_score = 70 if playbook != "remote_smb" else 58
    if signals.get("portal_or_data_fit"):
        proof_score += 18
    proof_score = min(100, proof_score)

    source_score = min(100, max(0, company.source_trust * 100))
    total = round(
        fit_score * 0.25
        + need_score * 0.30
        + contact_score * 0.20
        + proof_score * 0.15
        + source_score * 0.10,
        2,
    )

    score = LeadScore(
        company=company,
        fit_score=round(fit_score, 2),
        need_score=round(need_score, 2),
        contact_score=round(contact_score, 2),
        proof_score=round(proof_score, 2),
        source_score=round(source_score, 2),
        total_score=total,
        reasons=reasons[:8],
    )
    db.add(score)
    return score
