import os
from fastapi.templating import Jinja2Templates

# URL prefix for links when running behind a reverse proxy (e.g., /store in Cloud Run)
# Empty string for local development, "/store" for Cloud Run deployment
URL_PREFIX = os.getenv("URL_PREFIX", "")

# Shared Jinja2 template loader
# Note: other routers can import this to avoid duplicating template initialization.
templates = Jinja2Templates(directory="app/templates")

# Add URL_PREFIX as a global variable for all templates
templates.env.globals["url_prefix"] = URL_PREFIX

__all__ = ["templates", "URL_PREFIX"]
