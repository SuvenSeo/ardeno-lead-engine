from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class ContactInput(BaseModel):
    full_name: str | None = None
    role: str | None = None
    email: EmailStr
    email_type: str = "generic"
    email_status: str = "unknown"
    source: str = "manual"
    source_url: str | None = None
    provider_contact_id: str | None = None
    processing_basis: str = "public business contact"
    consent_notes: str | None = None


class CompanyInput(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    domain: str | None = None
    place_id: str | None = None
    website_url: HttpUrl | str | None = None
    country: str | None = "Sri Lanka"
    region: str | None = None
    city: str | None = None
    industry: str | None = None
    source_trust: float = Field(default=0.65, ge=0, le=1)
    source_url: str | None = None
    digital_footprint: dict[str, Any] = Field(default_factory=dict)
    contacts: list[ContactInput] = Field(default_factory=list)


class DiscoveryRunCreate(BaseModel):
    source_key: str = "manual"
    query: str = Field(default="manual import", max_length=300)
    location: str | None = None
    manual_companies: list[CompanyInput] = Field(default_factory=list)


class DraftCreate(BaseModel):
    campaign_id: str | None = None
    contact_id: str | None = None
    use_ai: bool = True


class ApprovalCreate(BaseModel):
    approver_email: EmailStr
    decision: str = Field(pattern="^(approved|rejected)$")
    notes: str | None = None


class SendCreate(BaseModel):
    sandbox: bool = True


class SuppressionCreate(BaseModel):
    value: str = Field(min_length=1, max_length=320)
    value_type: str = Field(pattern="^(email|domain|company)$")
    reason: str = Field(min_length=1, max_length=240)
    source: str = "manual"


class BounceWebhook(BaseModel):
    provider_message_id: str | None = None
    email: EmailStr | None = None
    message_id: str | None = None
    event: str = "bounce"
    reason: str | None = None


class ResearchRunCreate(BaseModel):
    profile_key: str = "clinics"
    location: str = "Sri Lanka"
    score_threshold: float | None = None
    max_companies: int | None = Field(default=None, ge=1, le=100)
    max_drafts: int | None = Field(default=None, ge=0, le=50)
    create_drafts: bool = True


class SmartleadWebhook(BaseModel):
    event: str
    email: EmailStr | None = None
    lead_id: str | None = None
    campaign_id: str | None = None
    message_id: str | None = None
    provider_message_id: str | None = None
    reply_text: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class LeadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    website_url: str | None
    country: str | None
    city: str | None
    industry: str | None
    status: str
    total_score: float | None = None
    score_reasons: list[str] = Field(default_factory=list)
    contact_count: int = 0
    latest_draft_status: str | None = None
    source_reason: str | None = None
    contact_quality: str | None = None
    research_profile: str | None = None


class ResearchRunResponse(BaseModel):
    id: str
    profile_key: str
    location: str
    status: str
    companies_seen: int
    companies_created: int
    companies_enriched: int
    drafts_created: int
    score_threshold: float
    source_summary: dict[str, Any]
    error: str | None = None


class MessageResponse(BaseModel):
    id: str
    status: str
    provider: str
    to_email: str
    from_email: str
