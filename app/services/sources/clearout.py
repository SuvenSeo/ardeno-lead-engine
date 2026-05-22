from __future__ import annotations

import httpx

from app.config import Settings
from app.services.compliance import normalize_email


class ClearoutNotConfigured(RuntimeError):
    pass


def _map_status(payload: dict) -> str:
    status = str(payload.get("status") or payload.get("safe_to_send") or payload.get("result") or "").lower()
    if status in {"valid", "verified", "deliverable", "yes", "true"}:
        return "deliverable"
    if status in {"invalid", "undeliverable", "no", "false"}:
        return "invalid"
    if status in {"risky", "catch_all", "accept_all", "unknown"}:
        return "risky"
    return "unknown"


async def verify_email(settings: Settings, *, email: str) -> tuple[str, dict]:
    if not settings.clearout_api_key:
        raise ClearoutNotConfigured("CLEAROUT_API_KEY is required for Clearout verification.")

    headers = {"Authorization": settings.clearout_api_key}
    params = {"email": normalize_email(email)}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.clearout.io/v2/email_verify/instant", params=params, headers=headers)
    response.raise_for_status()
    data = response.json()
    result = data.get("data") if isinstance(data.get("data"), dict) else data
    return _map_status(result), result
