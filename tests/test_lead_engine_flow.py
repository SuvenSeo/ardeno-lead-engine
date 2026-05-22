from __future__ import annotations

from tests.conftest import manual_payload


def create_lead(client, headers, email: str = "info@lotusbay.lk") -> str:
    response = client.post("/api/v1/discovery/runs", json=manual_payload(email), headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["companies_seen"] == 1
    assert data["leads"][0]["total_score"] > 70
    return data["leads"][0]["id"]


def create_approved_draft(client, headers, company_id: str) -> dict:
    draft_response = client.post(f"/api/v1/leads/{company_id}/drafts", json={}, headers=headers)
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    approval_response = client.post(
        f"/api/v1/drafts/{draft['id']}/approval",
        json={"approver_email": "ops@ardeno.studio", "decision": "approved"},
        headers=headers,
    )
    assert approval_response.status_code == 200, approval_response.text
    return approval_response.json()


def test_manual_discovery_scores_and_dedupes(client, admin_headers):
    company_id = create_lead(client, admin_headers)
    second = client.post("/api/v1/discovery/runs", json=manual_payload(), headers=admin_headers)
    assert second.status_code == 200, second.text
    assert second.json()["companies_created"] == 0

    lead = client.get(f"/api/v1/leads/{company_id}", headers=admin_headers).json()
    assert lead["company"]["name"] == "Lotus Bay Dental Clinic"
    assert lead["contacts"][0]["processing_basis"] == "public business contact"
    assert "source" in lead["contacts"][0]


def test_draft_constraints_and_approval_required(client, admin_headers):
    company_id = create_lead(client, admin_headers)
    draft_response = client.post(f"/api/v1/leads/{company_id}/drafts", json={}, headers=admin_headers)
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()

    assert draft["word_count"] <= 100
    assert "Ardeno Studio" in draft["compliance_footer"]
    assert "receiving this because" in draft["compliance_footer"]
    assert "Opt out:" in draft["compliance_footer"]
    assert "fake" not in draft["body"].lower()

    blocked = client.post(f"/api/v1/drafts/{draft['id']}/send", json={"sandbox": True}, headers=admin_headers)
    assert blocked.status_code == 400
    assert "approved" in blocked.json()["detail"]


def test_approved_sandbox_send_updates_metrics(client, admin_headers):
    company_id = create_lead(client, admin_headers)
    draft = create_approved_draft(client, admin_headers, company_id)
    response = client.post(f"/api/v1/drafts/{draft['id']}/send", json={"sandbox": True}, headers=admin_headers)
    assert response.status_code == 200, response.text
    message = response.json()
    assert message["status"] == "sandbox_queued"
    assert message["provider"] == "sandbox"

    metrics = client.get("/api/v1/metrics", headers=admin_headers).json()
    assert metrics["sent_or_queued"] == 1


def test_suppression_blocks_send(client, admin_headers):
    company_id = create_lead(client, admin_headers, email="hello@suppressed.lk")
    draft = create_approved_draft(client, admin_headers, company_id)
    suppression = client.post(
        "/api/v1/suppressions",
        json={
            "value_type": "email",
            "value": "hello@suppressed.lk",
            "reason": "manual opt-out",
            "source": "test",
        },
        headers=admin_headers,
    )
    assert suppression.status_code == 200, suppression.text

    response = client.post(f"/api/v1/drafts/{draft['id']}/send", json={"sandbox": True}, headers=admin_headers)
    assert response.status_code == 400
    assert "suppressed" in response.json()["detail"].lower()


def test_non_sandbox_send_fails_closed(client, admin_headers):
    company_id = create_lead(client, admin_headers)
    draft = create_approved_draft(client, admin_headers, company_id)
    response = client.post(f"/api/v1/drafts/{draft['id']}/send", json={"sandbox": False}, headers=admin_headers)
    assert response.status_code == 400
    assert "sandbox" in response.json()["detail"].lower()


def test_unsubscribe_and_bounce_create_global_suppression(client, admin_headers):
    unsub = client.get("/api/v1/unsubscribe?email=recipient@example.com")
    assert unsub.status_code == 200
    assert unsub.json()["status"] == "suppressed"

    bounce = client.post(
        "/api/v1/webhooks/bounce",
        json={"email": "bounced@example.com", "event": "bounce", "reason": "hard bounce"},
        headers=admin_headers,
    )
    assert bounce.status_code == 200, bounce.text

    metrics = client.get("/api/v1/metrics", headers=admin_headers).json()
    assert metrics["suppressed"] == 2
