from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app.models import Company, Contact, EnrichmentRun, LeadSource, SourceObservation, now_utc
from app.services.compliance import domain_from_email, domain_from_url, normalize_email

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _same_domain(base_url: str, candidate: str) -> bool:
    base = domain_from_url(base_url)
    other = domain_from_url(candidate)
    return bool(base and other and (base == other or other.endswith(f".{base}")))


async def _fetch_text(url: str) -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"User-Agent": "ArdenoLeadEngine/1.0"}) as client:
        response = await client.get(url)
    response.raise_for_status()
    return str(response.url), response.text[:300_000]


def _candidate_pages(base_url: str, html: str) -> list[str]:
    candidates = [base_url]
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        if any(term in href.lower() for term in ["contact", "about", "booking"]):
            full = urljoin(base_url, href)
            if _same_domain(base_url, full):
                candidates.append(full)
    return list(dict.fromkeys(candidates))[:4]


def _signals_from_html(url: str, html: str) -> dict:
    lower = html.lower()
    has_contact = "contact" in lower or "mailto:" in lower
    has_booking = any(term in lower for term in ["book now", "appointment", "reservation", "schedule"])
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:180] if title_match else None
    parsed = urlparse(url)
    return {
        "has_contact_page": has_contact,
        "missing_contact_flow": not has_contact,
        "missing_booking_flow": not has_booking,
        "low_digital_completeness": len(html) < 25_000,
        "slow_site": len(html) > 250_000,
        "ssl_enabled": parsed.scheme == "https",
        "page_title": title,
    }


async def enrich_company_website(db: Session, *, company: Company) -> EnrichmentRun:
    run = EnrichmentRun(company_id=company.id, source="company_website", status="running")
    db.add(run)
    db.flush()

    if not company.website_url:
        run.status = "failed"
        run.error = "Company has no website_url."
        run.finished_at = now_utc()
        return run

    source = db.query(LeadSource).filter(LeadSource.key == "company_website").first()
    seen_html: list[str] = []
    fetched_urls: list[str] = []
    try:
        canonical_url, home_html = await _fetch_text(company.website_url)
        fetched_urls.append(canonical_url)
        seen_html.append(home_html)
        for url in _candidate_pages(canonical_url, home_html)[1:]:
            try:
                fetched, html = await _fetch_text(url)
                fetched_urls.append(fetched)
                seen_html.append(html)
            except httpx.HTTPError:
                continue

        combined = "\n".join(seen_html)
        signals = _signals_from_html(canonical_url, combined)
        emails = sorted({normalize_email(match) for match in EMAIL_RE.findall(combined)})
        company.website_url = canonical_url
        company.domain = company.domain or domain_from_url(canonical_url)
        company.digital_footprint = {**(company.digital_footprint or {}), **signals}
        db.add(
            SourceObservation(
                company=company,
                source=source,
                url=canonical_url,
                raw_payload={"fetched_urls": fetched_urls, "emails_found": emails[:10]},
                signals=signals,
            )
        )

        company_domain = company.domain
        for email in emails[:5]:
            if company_domain and domain_from_email(email) and not domain_from_email(email).endswith(company_domain):
                continue
            existing = next((contact for contact in company.contacts if contact.email == email), None)
            if not existing:
                email_name = email.split("@", 1)[0]
                email_type = "generic" if email_name in {"info", "hello", "contact", "sales", "admin", "booking"} else "role"
                db.add(
                    Contact(
                        company=company,
                        email=email,
                        email_type=email_type,
                        email_status="unknown",
                        source="company_website",
                        source_url=canonical_url,
                        processing_basis="public business contact on company website",
                    )
                )

        run.status = "completed"
        run.summary = f"Fetched {len(fetched_urls)} pages; found {len(emails)} public emails."
    except httpx.HTTPError as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
    finally:
        run.finished_at = now_utc()
    return run
