# API Quick Reference

Set `X-Admin-Key` on every internal request.

## Manual Discovery

```http
POST /api/v1/discovery/runs
X-Admin-Key: dev-admin-key
Content-Type: application/json
```

```json
{
  "source_key": "manual",
  "query": "Sri Lanka SMB seed",
  "location": "Colombo, Sri Lanka",
  "manual_companies": [
    {
      "name": "Lotus Bay Dental Clinic",
      "website_url": "https://example.com",
      "country": "Sri Lanka",
      "city": "Colombo",
      "industry": "clinic dental health",
      "source_trust": 0.75,
      "source_url": "manual research note",
      "digital_footprint": {
        "weak_mobile_ux": true,
        "missing_booking_flow": true
      },
      "contacts": [
        {
          "email": "info@lotusbay.example",
          "email_type": "generic",
          "email_status": "verified",
          "processing_basis": "public business contact"
        }
      ]
    }
  ]
}
```

## Human Approval Flow

1. `POST /api/v1/research/runs`
2. `GET /api/v1/recommendations`
3. `POST /api/v1/leads/{company_id}/drafts`
4. `POST /api/v1/drafts/{draft_id}/approval`
5. `POST /api/v1/drafts/{draft_id}/approve-and-send`

## Autonomous Research

```json
{
  "profile_key": "clinics",
  "location": "Sri Lanka",
  "score_threshold": 72,
  "max_companies": 20,
  "max_drafts": 8,
  "create_drafts": true
}
```

Cron endpoint:

```http
GET /api/v1/cron/research
Authorization: Bearer <CRON_SECRET>
```

## Manual Approval Flow

1. `GET /api/v1/leads`
2. `POST /api/v1/leads/{company_id}/drafts`
3. `POST /api/v1/drafts/{draft_id}/approval`
4. `POST /api/v1/drafts/{draft_id}/send`

Sandbox send payload:

```json
{ "sandbox": true }
```

Production send payload:

```json
{ "sandbox": false }
```

Production send fails unless provider, sender authentication, footer, suppression, approval, and daily cap checks pass. For `SENDING_PROVIDER=smartlead`, the send request queues a lead into the configured Smartlead campaign and waits for Smartlead campaign scheduling.

## Smartlead Webhook

```json
{
  "event": "sent",
  "email": "lead@example.com",
  "lead_id": "smartlead-lead-id",
  "campaign_id": "smartlead-campaign-id"
}
```

## Suppression

```json
{
  "value_type": "email",
  "value": "contact@example.com",
  "reason": "manual opt-out",
  "source": "operator"
}
```

## Bounce Webhook

```json
{
  "message_id": "message-uuid",
  "event": "bounce",
  "reason": "hard bounce"
}
```
