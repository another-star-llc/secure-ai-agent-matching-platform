from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class WandbConfig:
    enabled: bool
    project: str
    entity: str
    run_id: str
    base_url: str


def init_wandb(config: WandbConfig):
    if not config.enabled:
        return None
    try:
        import wandb  # type: ignore
    except ImportError:  # pragma: no cover
        return None
    run = wandb.init(  # type: ignore[union-attr]
        project=config.project,
        entity=config.entity,
        id=config.run_id,
        name=config.run_id,
        resume="allow",
        reinit=True,
        settings=wandb.Settings(start_method="thread")  # type: ignore[attr-defined]
    )
    return run


def log_artifact(config: WandbConfig, path: Path, name: str, artifact_type: str = "judge") -> None:
    if not config.enabled:
        return
    if not path.exists():
        return
    try:
        import wandb  # type: ignore
    except ImportError:  # pragma: no cover
        return
    artifact = wandb.Artifact(name=name, type=artifact_type)  # type: ignore[attr-defined]
    artifact.add_file(str(path))
    wandb.log_artifact(artifact)  # type: ignore[attr-defined]


def export_metadata(config: Optional[WandbConfig]):
    if not config:
        return None
    url = f"{config.base_url.rstrip('/')}/{config.entity}/{config.project}/runs/{config.run_id}" if config.base_url else None
    return {
        "runId": config.run_id,
        "project": config.project,
        "entity": config.entity,
        "url": url
    }


def log_metrics(config: WandbConfig, metrics: Dict[str, float]) -> None:
    if not config.enabled or not metrics:
        return
    try:
        import wandb  # type: ignore
    except ImportError:  # pragma: no cover
        return
    wandb.log(metrics)  # type: ignore[attr-defined]


def update_config(config: WandbConfig, values: Dict[str, object]) -> None:
    if not config.enabled or not values:
        return
    try:
        import wandb  # type: ignore
    except ImportError:  # pragma: no cover
        return
    run = getattr(wandb, "run", None)
    if run is None:
        return
    try:
        wandb.config.update(values, allow_val_change=True)  # type: ignore[attr-defined]
    except Exception:
        # wandb.config may be frozen in some contexts; ignore update failures
        return
