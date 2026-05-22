from __future__ import annotations

import httpx

from app.config import Settings


class GooglePlacesNotConfigured(RuntimeError):
    pass


GOOGLE_PLACES_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.websiteUri",
        "places.businessStatus",
        "places.types",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
    ]
)


async def text_search(settings: Settings, *, query: str, location: str | None = None, limit: int = 10) -> list[dict]:
    if not settings.google_places_api_key:
        raise GooglePlacesNotConfigured("GOOGLE_PLACES_API_KEY is required for Google Places discovery.")

    text_query = f"{query} {location}".strip() if location else query
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": GOOGLE_PLACES_FIELD_MASK,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://places.googleapis.com/v1/places:searchText",
            json={"textQuery": text_query, "pageSize": min(limit, 20)},
            headers=headers,
        )
    response.raise_for_status()
    return response.json().get("places", [])
