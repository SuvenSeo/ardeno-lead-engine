from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("name", "website_url", name="uq_company_name_website"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), index=True)
    domain: Mapped[str | None] = mapped_column(String(240), index=True)
    place_id: Mapped[str | None] = mapped_column(String(240), unique=True, index=True)
    website_url: Mapped[str | None] = mapped_column(String(600))
    country: Mapped[str | None] = mapped_column(String(120), index=True)
    region: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(160))
    industry: Mapped[str | None] = mapped_column(String(160), index=True)
    source_trust: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    research_profile: Mapped[str | None] = mapped_column(String(120), index=True)
    digital_footprint: Mapped[dict] = mapped_column(JSON, default=dict)
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)

    contacts: Mapped[list[Contact]] = relationship(back_populates="company", cascade="all, delete-orphan")
    observations: Mapped[list[SourceObservation]] = relationship(back_populates="company", cascade="all, delete-orphan")
    scores: Mapped[list[LeadScore]] = relationship(back_populates="company", cascade="all, delete-orphan")
    drafts: Mapped[list[EmailDraft]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("company_id", "email", name="uq_company_contact_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str | None] = mapped_column(String(240))
    role: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), index=True)
    email_type: Mapped[str] = mapped_column(String(40), default="generic")
    email_status: Mapped[str] = mapped_column(String(40), default="unknown")
    source: Mapped[str] = mapped_column(String(120), default="manual")
    source_url: Mapped[str | None] = mapped_column(String(600))
    provider_contact_id: Mapped[str | None] = mapped_column(String(240))
    processing_basis: Mapped[str] = mapped_column(String(160), default="public business contact")
    consent_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    company: Mapped[Company] = relationship(back_populates="contacts")
    drafts: Mapped[list[EmailDraft]] = relationship(back_populates="contact")


class LeadSource(Base):
    __tablename__ = "lead_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(80))
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    terms_url: Mapped[str | None] = mapped_column(String(600))
    allowed_use_notes: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    observations: Mapped[list[SourceObservation]] = relationship(back_populates="source")


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_key: Mapped[str] = mapped_column(String(120), index=True)
    query: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(40), default="created")
    companies_created: Mapped[int] = mapped_column(Integer, default=0)
    companies_seen: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_key: Mapped[str] = mapped_column(String(120), index=True)
    location: Mapped[str] = mapped_column(String(240), default="Sri Lanka")
    status: Mapped[str] = mapped_column(String(40), default="created", index=True)
    source_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    companies_seen: Mapped[int] = mapped_column(Integer, default=0)
    companies_created: Mapped[int] = mapped_column(Integer, default=0)
    companies_enriched: Mapped[int] = mapped_column(Integer, default=0)
    drafts_created: Mapped[int] = mapped_column(Integer, default=0)
    score_threshold: Mapped[float] = mapped_column(Float, default=72)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class SourceObservation(Base):
    __tablename__ = "source_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("lead_sources.id"), index=True)
    url: Mapped[str | None] = mapped_column(String(600))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)

    company: Mapped[Company] = relationship(back_populates="observations")
    source: Mapped[LeadSource | None] = relationship(back_populates="observations")


class EnrichmentRun(Base):
    __tablename__ = "enrichment_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="created")
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class LeadScore(Base):
    __tablename__ = "lead_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    fit_score: Mapped[float] = mapped_column(Float, default=0)
    need_score: Mapped[float] = mapped_column(Float, default=0)
    contact_score: Mapped[float] = mapped_column(Float, default=0)
    proof_score: Mapped[float] = mapped_column(Float, default=0)
    source_score: Mapped[float] = mapped_column(Float, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    company: Mapped[Company] = relationship(back_populates="scores")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), unique=True)
    icp_key: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    sender_email: Mapped[str | None] = mapped_column(String(320))
    daily_cap: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    drafts: Mapped[list[EmailDraft]] = relationship(back_populates="campaign")


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), index=True)
    subject: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    concrete_reason: Mapped[str] = mapped_column(String(400))
    proof_angle: Mapped[str] = mapped_column(String(240))
    source_reason: Mapped[str | None] = mapped_column(String(600))
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    prompt_input: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    compliance_footer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    company: Mapped[Company] = relationship(back_populates="drafts")
    contact: Mapped[Contact | None] = relationship(back_populates="drafts")
    campaign: Mapped[Campaign | None] = relationship(back_populates="drafts")
    approvals: Mapped[list[SendApproval]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    messages: Mapped[list[Message]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class SendApproval(Base):
    __tablename__ = "send_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("email_drafts.id", ondelete="CASCADE"), index=True)
    approver_email: Mapped[str] = mapped_column(String(320))
    decision: Mapped[str] = mapped_column(String(40), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    draft: Mapped[EmailDraft] = relationship(back_populates="approvals")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("email_drafts.id", ondelete="CASCADE"), index=True)
    to_email: Mapped[str] = mapped_column(String(320), index=True)
    from_email: Mapped[str] = mapped_column(String(320), index=True)
    provider: Mapped[str] = mapped_column(String(80), default="sandbox")
    provider_message_id: Mapped[str | None] = mapped_column(String(240))
    provider_lead_id: Mapped[str | None] = mapped_column(String(240))
    provider_campaign_id: Mapped[str | None] = mapped_column(String(240))
    provider_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(80), default="created", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)

    draft: Mapped[EmailDraft] = relationship(back_populates="messages")


class SuppressionEntry(Base):
    __tablename__ = "suppression_list"
    __table_args__ = (UniqueConstraint("value_type", "value", name="uq_suppression_value"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    value: Mapped[str] = mapped_column(String(320), index=True)
    value_type: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(String(240))
    source: Mapped[str] = mapped_column(String(120), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(160), default="system", index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
