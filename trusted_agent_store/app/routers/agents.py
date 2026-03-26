from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from typing import List, Optional
from datetime import datetime

from app.services.agent_registry import load_agents, save_agents
from app.dependencies import templates


router = APIRouter(prefix="/agents", tags=["agents"])
api_router = APIRouter(prefix="/api/agents", tags=["agents-api"])


@router.get("", response_class=HTMLResponse)
async def list_agents(request: Request):
    agents = load_agents()
    # sort by updated_at desc if present
    agents_sorted = sorted(agents, key=lambda a: a.updated_at or a.created_at or "", reverse=True)
    return templates.TemplateResponse(
        "agents.html",
        {
            "request": request,
            "agents": agents_sorted,
        },
    )


@api_router.get("")
async def api_list_agents(status: Optional[str] = None, provider: Optional[str] = None, limit: int = 100, offset: int = 0):
    agents = load_agents()
    if status:
        agents = [a for a in agents if a.status == status]
    if provider:
        agents = [a for a in agents if a.provider == provider]
    agents_sorted = sorted(agents, key=lambda a: a.updated_at or a.created_at or "", reverse=True)
    sliced = agents_sorted[offset: offset + limit]
    return {
        "items": [a.__dict__ for a in sliced],
        "total": len(agents_sorted),
        "limit": limit,
        "offset": offset,
    }


@api_router.patch("/{agent_id}/trust")
async def api_update_trust(agent_id: str, payload: dict):
    agents = load_agents()
    found = False
    for a in agents:
        if a.id == agent_id:
            found = True
            # バリデーションは上位(Cloud Run IAM)で想定。値はそのまま上書き。
            if "trust_score" in payload:
                a.trust_score = payload.get("trust_score")
            if "trust_score" in payload:
                a.trust_score = payload.get("trust_score")
            a.updated_at = datetime.utcnow().isoformat()
            break
    if not found:
        raise HTTPException(status_code=404, detail="agent not found")
    save_agents(agents)
    return {"id": agent_id, "updated_at": a.updated_at, "trust_score": a.trust_score}
