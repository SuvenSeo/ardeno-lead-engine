from __future__ import annotations

import json

import httpx

from app.config import Settings
from app.models import Company, Contact, LeadScore


DRAFT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subject": {"type": "string", "maxLength": 90},
        "body": {"type": "string", "maxLength": 900},
        "reason": {"type": "string", "maxLength": 240},
        "proof_angle": {"type": "string", "maxLength": 180},
        "source_reason": {"type": "string", "maxLength": 320},
        "risk_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
    },
    "required": ["subject", "body", "reason", "proof_angle", "source_reason", "risk_flags"],
}


class OpenAIDraftNotConfigured(RuntimeError):
    pass


def build_prompt_input(company: Company, contact: Contact, score: LeadScore | None) -> dict:
    signals = company.digital_footprint or {}
    return {
        "company": {
            "name": company.name,
            "website_url": company.website_url,
            "country": company.country,
            "city": company.city,
            "industry": company.industry,
            "research_profile": company.research_profile,
        },
        "contact": {
            "email": contact.email,
            "email_type": contact.email_type,
            "email_status": contact.email_status,
            "processing_basis": contact.processing_basis,
            "source_url": contact.source_url,
        },
        "score": {
            "total": score.total_score if score else None,
            "reasons": score.reasons if score else [],
        },
        "signals": signals,
    }


async def generate_structured_draft(
    settings: Settings,
    *,
    prompt_input: dict,
) -> tuple[dict, dict]:
    if not settings.openai_api_key:
        raise OpenAIDraftNotConfigured("OPENAI_API_KEY is required for AI-assisted drafting.")

    instructions = (
        "Write one compliant cold outreach email draft for Ardeno Studio. "
        "Use only the provided sourced facts. Do not pretend prior relationship. "
        "Body must be under 100 words. Include one concrete reason and one Ardeno proof angle. "
        "No fake familiarity, no unverifiable claims, no pressure language."
    )
    payload = {
        "model": settings.openai_draft_model,
        "input": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(prompt_input, ensure_ascii=True)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ardeno_outreach_draft",
                "strict": True,
                "schema": DRAFT_JSON_SCHEMA,
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.openai.com/v1/responses", json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    text = data.get("output_text")
    if not text:
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    text = content["text"]
                    break
            if text:
                break
    if not text:
        raise ValueError("OpenAI response did not include output_text.")
    return json.loads(text), {"provider": "openai", "model": settings.openai_draft_model, "response_id": data.get("id")}
