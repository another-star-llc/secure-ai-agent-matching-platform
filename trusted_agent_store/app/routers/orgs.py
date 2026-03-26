from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from app.dependencies import templates
from app.services.org_registry import Organization, add_org, load_orgs, new_org_id


router = APIRouter(prefix="/orgs", tags=["orgs-ui"])
api_router = APIRouter(prefix="/api/orgs", tags=["orgs-api"])


@router.get("/register", response_class=HTMLResponse)
async def register_org_form(request: Request):
    return templates.TemplateResponse("register_org.html", {"request": request})


@api_router.get("")
async def list_orgs(limit: int = 100, offset: int = 0):
    orgs = load_orgs()
    orgs_sorted = sorted(orgs, key=lambda o: o.updated_at or o.created_at or "", reverse=True)
    sliced = orgs_sorted[offset : offset + limit]
    return {"items": [o.__dict__ for o in sliced], "total": len(orgs_sorted), "limit": limit, "offset": offset}


@api_router.post("")
async def create_org(payload: dict):
    name = payload.get("name")
    email = payload.get("contact_email")
    if not name or not email:
        raise HTTPException(status_code=400, detail="name and contact_email are required")

    now = datetime.utcnow().isoformat()
    org = Organization(
        id=new_org_id(),
        name=name,
        contact_email=email,
        website_url=payload.get("website_url"),
        industry=payload.get("industry"),
        description=payload.get("description"),
        created_at=now,
        updated_at=now,
    )
    add_org(org)
    return org.__dict__
