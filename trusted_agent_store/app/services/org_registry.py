"""Simple file-based organization registry (PoC).

Stores organizations in JSON at /app/data/orgs/organizations.json.
Mimics agent_registry but keeps schema minimal for PoC.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional


# Support both Docker (/app/data) and local development (./data)
_docker_path = "/app/data/orgs/organizations.json"
_local_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "orgs" / "organizations.json")
_default_path = _docker_path if Path("/app").exists() else _local_path
REGISTRY_PATH = Path(os.getenv("ORG_REGISTRY_PATH", _default_path))


@dataclass
class Organization:
    id: str
    name: str
    contact_email: str
    website_url: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _ensure_file() -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text("[]", encoding="utf-8")


def load_orgs() -> List[Organization]:
    _ensure_file()
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [Organization(**item) for item in data]


def save_orgs(entries: List[Organization]) -> None:
    _ensure_file()
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


def add_org(entry: Organization) -> None:
    orgs = load_orgs()
    orgs.append(entry)
    save_orgs(orgs)


def new_org_id() -> str:
    return str(uuid.uuid4())
