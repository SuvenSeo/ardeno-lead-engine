from __future__ import annotations

from datetime import datetime, time
from urllib.parse import quote_plus, urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Company, EmailDraft, Message, SuppressionEntry, now_utc


class ComplianceError(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def domain_from_email(email: str) -> str | None:
    email = normalize_email(email)
    if "@" not in email:
        return None
    return email.rsplit("@", 1)[1]


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    hostname = parsed.hostname
    if not hostname:
        return None
    return hostname[4:] if hostname.startswith("www.") else hostname


def normalize_suppression_value(value: str, value_type: str) -> str:
    value = value.strip().lower()
    if value_type == "domain":
        return domain_from_url(value) or value
    return value


def company_domains(company: Company) -> set[str]:
    domains = set()
    if company.domain:
        domains.add(normalize_suppression_value(company.domain, "domain"))
    if company.website_url:
        domain = domain_from_url(company.website_url)
        if domain:
            domains.add(domain)
    return domains


def suppression_matches(db: Session, *, email: str | None = None, company: Company | None = None) -> SuppressionEntry | None:
    values: list[tuple[str, str]] = []
    if email:
        normalized = normalize_email(email)
        values.append(("email", normalized))
        email_domain = domain_from_email(normalized)
        if email_domain:
            values.append(("domain", email_domain))

    if company:
        values.append(("company", company.id.lower()))
        values.append(("company", company.name.strip().lower()))
        for domain in company_domains(company):
            values.append(("domain", domain))

    if not values:
        return None

    clauses = [
        (SuppressionEntry.value_type == value_type) & (SuppressionEntry.value == value)
        for value_type, value in values
    ]
    return db.scalar(select(SuppressionEntry).where(or_(*clauses)).limit(1))


def add_suppression(
    db: Session,
    *,
    value: str,
    value_type: str,
    reason: str,
    source: str = "manual",
) -> SuppressionEntry:
    normalized = normalize_suppression_value(value, value_type)
    existing = db.scalar(
        select(SuppressionEntry).where(
            SuppressionEntry.value_type == value_type,
            SuppressionEntry.value == normalized,
        )
    )
    if existing:
        existing.reason = reason
        existing.source = source
        return existing
    entry = SuppressionEntry(value=normalized, value_type=value_type, reason=reason, source=source)
    db.add(entry)
    return entry


def make_compliance_footer(settings: Settings, recipient_email: str) -> str:
    unsubscribe = f"{settings.outreach_unsubscribe_base_url}?email={quote_plus(normalize_email(recipient_email))}"
    return (
        f"{settings.outreach_company_name} | {settings.outreach_postal_address}\n"
        f"You are receiving this because your public business details suggest a fit for Ardeno Studio services.\n"
        f"Opt out: {unsubscribe}"
    )


def assert_footer_is_valid(draft: EmailDraft, settings: Settings, *, production: bool) -> None:
    combined = f"{draft.body}\n{draft.compliance_footer}".lower()
    required = [
        settings.outreach_company_name.lower(),
        "opt out",
        "receiving this because",
    ]
    missing = [term for term in required if term not in combined]
    if missing:
        raise ComplianceError(f"Draft is missing compliance text: {', '.join(missing)}")
    if production and "set a valid physical mailing address" in settings.outreach_postal_address.lower():
        raise ComplianceError("Production sending requires a real physical mailing address.")


def assert_sender_ready(settings: Settings, *, sandbox: bool) -> None:
    if sandbox:
        return
    if settings.sending_provider == "sandbox":
        raise ComplianceError("Non-sandbox send requested, but SENDING_PROVIDER is sandbox.")
    if settings.require_dns_auth and not settings.sender_dns_auth_verified:
        raise ComplianceError("Sender DNS/auth is not verified. Set SENDER_DNS_AUTH_VERIFIED=true only after SPF, DKIM, DMARC, reply mailbox, and monitoring are confirmed.")
    if settings.sending_provider == "resend" and not settings.resend_api_key:
        raise ComplianceError("RESEND_API_KEY is required for Resend sending.")


def assert_daily_cap(db: Session, *, sender: str, cap: int) -> None:
    today = datetime.combine(now_utc().date(), time.min)
    count = db.scalar(
        select(func.count(Message.id)).where(
            Message.from_email == sender,
            Message.sent_at >= today,
            Message.status.in_(["sandbox_queued", "sent", "provider_queued"]),
        )
    )
    if count is not None and count >= cap:
        raise ComplianceError(f"Daily cap reached for {sender}: {count}/{cap}.")


def assert_draft_sendable(db: Session, *, draft: EmailDraft, settings: Settings, sandbox: bool) -> None:
    if draft.status != "approved":
        raise ComplianceError("Draft must be approved before sending.")
    if not draft.contact:
        raise ComplianceError("Draft needs a contact before sending.")
    suppressed = suppression_matches(db, email=draft.contact.email, company=draft.company)
    if suppressed:
        raise ComplianceError(f"Recipient is suppressed by {suppressed.value_type}:{suppressed.value}.")
    assert_sender_ready(settings, sandbox=sandbox)
    assert_footer_is_valid(draft, settings, production=not sandbox)
    assert_daily_cap(db, sender=settings.outreach_from_email, cap=settings.daily_send_cap_per_sender)
