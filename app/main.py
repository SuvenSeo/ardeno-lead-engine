from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api import router
from app.db import SessionLocal, init_db
from app.services.seed import seed_defaults


app = FastAPI(title="Ardeno Lead Engine", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_defaults(db)
        db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return (Path(__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
