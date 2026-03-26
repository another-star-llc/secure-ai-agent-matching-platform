"""Simple file-based agent registry.

Stores registered agents in JSON at /app/data/agents/registered-agents.json
(host bind: trusted_agent_store/data/agents/registered-agents.json).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

import os

# Support both Docker (/app/data) and local development (./data)
_docker_path = "/app/data/agents/registered-agents.json"
_local_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "agents" / "registered-agents.json")
_default_path = _docker_path if Path("/app").exists() else _local_path
REGISTRY_PATH = Path(os.getenv("REGISTRY_PATH", _default_path))


@dataclass
class AgentEntry:
    id: str
    name: str
    provider: str
    agent_card_url: Optional[str] = None
    endpoint_url: Optional[str] = None
    token_hint: Optional[str] = None  # store only a masked hint
    status: str = "active"
    use_cases: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Evaluation scores
    trust_score: Optional[int] = None


def _ensure_file() -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text("[]", encoding="utf-8")


def load_agents() -> List[AgentEntry]:
    _ensure_file()
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [AgentEntry(**item) for item in data]


def save_agents(entries: List[AgentEntry]) -> None:
    _ensure_file()
    tmp_path = REGISTRY_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(REGISTRY_PATH)


def upsert_agent(entry: AgentEntry) -> None:
    agents = load_agents()
    by_id = {a.id: a for a in agents}
    by_id[entry.id] = entry
    save_agents(list(by_id.values()))


def delete_agent(agent_id: str) -> None:
    agents = [a for a in load_agents() if a.id != agent_id]
    save_agents(agents)


def new_agent_id() -> str:
    return str(uuid.uuid4())
