from __future__ import annotations

from app.config import Settings, get_settings
from app.models import Contact
from app.services.research import generate_queries
from app.services.smartlead import build_smartlead_payload


def test_generate_queries_for_profile():
    queries = generate_queries("clinics", "Sri Lanka")
    assert "dental clinic Colombo Sri Lanka" in queries
    assert "doctor clinic Galle Sri Lanka" in queries


def test_research_run_discovers_enriches_scores_and_drafts(client, admin_headers, monkeypatch):
    async def fake_text_search(settings, *, query, location=None, limit=10):
        return [
            {
                "id": "places/test-clinic",
                "displayName": {"text": "Ardeno Test Clinic"},
                "formattedAddress": "Colombo, Sri Lanka",
                "websiteUri": "https://testclinic.lk",
                "businessStatus": "OPERATIONAL",
                "types": ["dental_clinic"],
                "rating": 4.5,
                "userRatingCount": 18,
            }
        ]

    async def fake_enrich(db, *, company):
        company.domain = "testclinic.lk"
        company.digital_footprint = {
            **(company.digital_footprint or {}),
            "weak_mobile_ux": True,
            "missing_booking_flow": True,
            "portal_or_data_fit": True,
        }
        if not company.contacts:
            db.add(
                Contact(
                    company=company,
                    email="info@testclinic.lk",
                    email_type="generic",
                    email_status="deliverable",
                    source="company_website",
                    source_url="https://testclinic.lk/contact",
                    processing_basis="public business contact on company website",
                )
            )

        class Run:
            status = "completed"

        return Run()

    monkeypatch.setattr("app.services.research.text_search", fake_text_search)
    monkeypatch.setattr("app.services.research.enrich_company_website", fake_enrich)

    response = client.post(
        "/api/v1/research/runs",
        json={
            "profile_key": "clinics",
            "location": "Sri Lanka",
            "score_threshold": 50,
            "max_companies": 1,
            "max_drafts": 1,
            "create_drafts": True,
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["companies_seen"] == 1
    assert data["drafts_created"] == 1

    recommendations = client.get("/api/v1/recommendations", headers=admin_headers).json()
    assert recommendations[0]["name"] == "Ardeno Test Clinic"
    assert recommendations[0]["contact_quality"] == "verified"


def test_cron_research_requires_secret(client):
    missing = client.get("/api/v1/cron/research")
    assert missing.status_code == 401


def test_vercel_requires_postgres_database_url(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings()
    assert settings.requires_persistent_database is True

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.neon.tech/ardeno")
    settings = Settings()
    assert settings.requires_persistent_database is False


def test_smartlead_approve_and_send_maps_payload(client, admin_headers, monkeypatch):
    from tests.conftest import manual_payload

    monkeypatch.setenv("SENDING_PROVIDER", "smartlead")
    monkeypatch.setenv("SMARTLEAD_API_KEY", "test-smartlead-key")
    monkeypatch.setenv("SMARTLEAD_CAMPAIGN_ID", "12345")
    monkeypatch.setenv("SENDER_DNS_AUTH_VERIFIED", "true")
    monkeypatch.setenv("OUTREACH_POSTAL_ADDRESS", "Ardeno Studio, Colombo, Sri Lanka")
    get_settings.cache_clear()

    created = client.post("/api/v1/discovery/runs", json=manual_payload(), headers=admin_headers)
    company_id = created.json()["leads"][0]["id"]
    draft = client.post(f"/api/v1/leads/{company_id}/drafts", json={"use_ai": False}, headers=admin_headers).json()

    captured = {}

    async def fake_add_lead(settings, *, draft):
        captured["payload"] = build_smartlead_payload(draft, settings)
        return "smartlead-lead-1", {"status": "ok", "message": "queued"}

    monkeypatch.setattr("app.services.email_sender.add_lead_to_campaign", fake_add_lead)
    response = client.post(
        f"/api/v1/drafts/{draft['id']}/approve-and-send",
        json={"sandbox": False},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    message = response.json()
    assert message["provider"] == "smartlead"
    assert message["status"] == "queued_in_smartlead"
    assert captured["payload"]["lead_list"][0]["email"] == "info@lotusbay.lk"
    assert captured["payload"]["settings"]["ignore_global_block_list"] is False
    get_settings.cache_clear()


def test_smartlead_webhook_updates_message_and_suppression(client, admin_headers, monkeypatch):
    # Record by email is accepted even if Smartlead cannot map to a local message yet.
    response = client.post(
        "/api/v1/webhooks/smartlead",
        json={"event": "unsubscribe", "email": "optout@example.com", "lead_id": "lead-1"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    metrics = client.get("/api/v1/metrics", headers=admin_headers).json()
    assert metrics["suppressed"] == 1
