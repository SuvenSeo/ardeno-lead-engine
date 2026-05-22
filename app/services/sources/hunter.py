from __future__ import annotations

import httpx

from app.config import Settings
from app.services.compliance import normalize_email


class HunterNotConfigured(RuntimeError):
    pass


async def domain_search(settings: Settings, *, domain: str, limit: int = 5) -> list[dict]:
    if not settings.hunter_api_key:
        raise HunterNotConfigured("HUNTER_API_KEY is required for Hunter enrichment.")

    params = {
        "domain": domain,
        "limit": min(limit, 10),
        "api_key": settings.hunter_api_key,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.hunter.io/v2/domain-search", params=params)
    response.raise_for_status()
    data = response.json().get("data", {})
    contacts: list[dict] = []
    for item in data.get("emails") or []:
        email = item.get("value")
        if not email:
            continue
        email_type = "generic" if item.get("type") == "generic" else "role"
        contacts.append(
            {
                "email": normalize_email(email),
                "full_name": " ".join(filter(None, [item.get("first_name"), item.get("last_name")])) or None,
                "role": item.get("position") or item.get("department"),
                "email_type": email_type,
                "email_status": "unknown",
                "source": "hunter",
                "source_url": f"https://hunter.io/search/{domain}",
                "provider_contact_id": item.get("linkedin") or item.get("twitter"),
                "processing_basis": "business contact returned by Hunter domain search",
            }
        )
    return contacts
