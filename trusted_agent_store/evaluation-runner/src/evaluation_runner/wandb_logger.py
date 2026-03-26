from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class WandbLogger:
  """Simple helper to attach stage artifacts/logs to a shared W&B run."""

  def __init__(
    self,
    *,
    enabled: bool,
    project: str,
    entity: str,
    run_id: str,
    base_url: str,
  ) -> None:
    self.enabled = enabled
    self.project = project
    self.entity = entity
    self.run_id = run_id
    self.base_url = base_url.rstrip("/")
    self.stage_logs: Dict[str, Dict[str, Any]] = {}

  @property
  def url(self) -> str:
    return f"{self.base_url}/{self.entity}/{self.project}/runs/{self.run_id}" if self.base_url else self.run_id

  def log_stage_summary(self, stage: str, summary: Dict[str, Any]) -> None:
    self.stage_logs[stage] = summary
    if not self.enabled:
      return
    try:
      import wandb  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
      return
    numeric_metrics: Dict[str, float] = {}
    for key, value in summary.items():
      metric_key = f"{stage}/{key}"
      if isinstance(value, (int, float)):
        numeric_metrics[metric_key] = float(value)
      elif isinstance(value, dict):
        for sub_key, sub_value in value.items():
          if isinstance(sub_value, (int, float)):
            numeric_metrics[f"{stage}/{key}/{sub_key}"] = float(sub_value)
    log_payload = {f"{stage}/summary": summary}
    if numeric_metrics:
      log_payload.update(numeric_metrics)
    wandb.log(log_payload)  # type: ignore[attr-defined]

  def save_artifact(self, stage: str, path: Path, name: Optional[str] = None) -> None:
    if not self.enabled:
      return
    if not path.exists():
      return
    try:
      import wandb  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
      return
    artifact = wandb.Artifact(name or f"{stage}-artifacts", type="security")  # type: ignore[attr-defined]
    artifact.add_file(str(path))
    wandb.log_artifact(artifact)  # type: ignore[attr-defined]

  def export_metadata(self) -> Dict[str, Any]:
    return {
      "runId": self.run_id,
      "project": self.project,
      "entity": self.entity,
      "url": self.url,
      "stages": self.stage_logs
    }


def create_wandb_logger(
  *,
  base_metadata: Dict[str, Any],
  wandb_info: Dict[str, Any],
  project: str,
  entity: str,
  base_url: str
) -> WandbLogger:
  enabled = bool(wandb_info.get("enabled"))
  run_id = wandb_info.get("runId") or base_metadata.get("wandb", {}).get("runId") or base_metadata.get("runId") or "sandbox"
  return WandbLogger(
    enabled=enabled,
    project=project,
    entity=entity,
    run_id=run_id,
    base_url=base_url,
  )
