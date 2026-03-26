import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from .database import engine, Base
from .routers import submissions, reviews, ui, agents, orgs, sse
from app.services.agent_registry import load_agents
from app.services.org_registry import load_orgs

# Base directory for static files and templates
# Defaults to Docker structure, can be overridden via environment variable
BASE_DIR = os.getenv("APP_BASE_DIR", "")

# URL prefix for links when running behind a reverse proxy (e.g., /store in Cloud Run)
# Empty string for local development, "/store" for Cloud Run deployment
URL_PREFIX = os.getenv("URL_PREFIX", "")

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Trusted Agent Store")

# Mount static files
static_dir = os.path.join(BASE_DIR, "static") if BASE_DIR else "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Setup templates
templates_dir = os.path.join(BASE_DIR, "app/templates") if BASE_DIR else "app/templates"
templates = Jinja2Templates(directory=templates_dir)

# Add URL_PREFIX as a global variable for all templates
templates.env.globals["url_prefix"] = URL_PREFIX

# Include routers
app.include_router(submissions.router)
app.include_router(reviews.router)
app.include_router(ui.router)
app.include_router(agents.router)
app.include_router(agents.api_router)
app.include_router(orgs.router)
app.include_router(orgs.api_router)
app.include_router(sse.router)         # SSE for real-time jury judge updates


@app.on_event("startup")
async def startup_event():
    """Initialize SSE manager with the main event loop."""
    sse_manager = sse.get_sse_manager()
    sse_manager.set_main_loop(asyncio.get_running_loop())


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    agents_list = load_agents()
    orgs_list = load_orgs()
    # Sort by updated_at (or created_at) descending (newest first)
    agents_sorted = sorted(
        agents_list,
        key=lambda a: a.updated_at or a.created_at or "",
        reverse=True
    )
    orgs_sorted = sorted(
        orgs_list,
        key=lambda o: o.updated_at or o.created_at or "",
        reverse=True
    )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "agents": agents_sorted,
            "orgs": orgs_sorted,
        },
    )

@app.get("/health")
async def health_check():
    return {"status": "ok"}
