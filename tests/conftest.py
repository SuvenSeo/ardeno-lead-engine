from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).parent / "_test_lead_engine.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["SENDING_PROVIDER"] = "sandbox"
os.environ["SENDER_DNS_AUTH_VERIFIED"] = "false"

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed import seed_defaults  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_defaults(db)
        db.commit()
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_headers():
    return {"X-Admin-Key": "test-admin-key"}


def manual_payload(email: str = "info@lotusbay.lk") -> dict:
    return {
        "source_key": "manual",
        "query": "Sri Lanka SMB seed",
        "location": "Colombo, Sri Lanka",
        "manual_companies": [
            {
                "name": "Lotus Bay Dental Clinic",
                "website_url": "https://lotusbay.lk",
                "country": "Sri Lanka",
                "city": "Colombo",
                "industry": "clinic dental health",
                "source_trust": 0.75,
                "source_url": "manual research note",
                "digital_footprint": {
                    "weak_mobile_ux": True,
                    "missing_booking_flow": True,
                    "portal_or_data_fit": True,
                },
                "contacts": [
                    {
                        "email": email,
                        "email_type": "generic",
                        "email_status": "verified",
                        "processing_basis": "public business contact",
                    }
                ],
            }
        ],
    }
