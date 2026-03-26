"""Minimal MCTS-style orchestrator stub for Judge Panel.

This module provides a lightweight orchestrator that can run multiple rollouts of
the stage-based Multi-Model Judge Panel and record simple UCB-style scores.

Current implementation is intentionally conservative (default 1 rollout) to avoid
extra latency while wiring the interface; it can be extended later with true tree
expansion and per-scenario branching.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, List, Any


@dataclass
class MCTSParams:
    # 一つのシナリオを何回ロールアウト（再評価）するか。直列で実行されるので増やすとリクエスト数が線形に増える。
    max_rollouts: int = int(os.getenv("JUDGE_MCTS_MAX_ROLLOUTS", "1"))
    # UCB1 の探索係数。大きいほど未探索パスを選びやすい。
    ucb_c: float = float(os.getenv("JUDGE_MCTS_UCB_C", "1.4"))
    # Minority veto 用の閾値（例: 0.3 なら30%以上で veto 扱い）。
    veto_threshold: float = float(os.getenv("JUDGE_VETO_THRESHOLD", "0.3"))


@dataclass
class RolloutResult:
    rollout_id: int
    verdict: str
    task_completion: int
    tool: int
    autonomy: int
    safety: int
    elapsed_ms: float


def orchestrate_mcts(
    *,
    scenarios: List[Dict[str, Any]],
    eval_fn: Callable[[], Dict[str, Any]],
    output_dir: Path,
    params: MCTSParams | None = None,
) -> Dict[str, Any]:
    """
    Run up to max_rollouts evaluations and pick best by UCB-style score.

    Note: For now we simply rerun the whole stage-based evaluation; tree branching
    is a TODO. This keeps behavior backward-compatible while providing a place to
    plug future MCTS logic.
    """

    params = params or MCTSParams()
    rollouts: List[RolloutResult] = []
    best_score = -1.0
    best_summary: Dict[str, Any] | None = None

    total_visits = 0
    for r in range(params.max_rollouts):
        start = time.perf_counter()
        summary = eval_fn()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        total_visits += 1

        # simple utility score: average of four sub-scores (0-100)
        utility = (
            summary.get("taskCompletion", 0)
            + summary.get("tool", 0)
            + summary.get("autonomy", 0)
            + summary.get("safety", 0)
        ) / 4.0 / 100.0

        # UCB1 term (exploration)
        ucb = utility + params.ucb_c * math.sqrt(math.log(max(total_visits, 1)) / max(total_visits, 1))

        rollouts.append(
            RolloutResult(
                rollout_id=r,
                verdict=summary.get("verdict", "manual"),
                task_completion=summary.get("taskCompletion", 0),
                tool=summary.get("tool", 0),
                autonomy=summary.get("autonomy", 0),
                safety=summary.get("safety", 0),
                elapsed_ms=elapsed_ms,
            )
        )

        if ucb > best_score:
            best_score = ucb
            best_summary = summary

        # Minority Veto shortcut
        if summary.get("verdict") == "reject":
            best_summary = summary
            break

    # persist rollout log
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "mcts_rollouts.jsonl").open("w", encoding="utf-8") as f:
        for r in rollouts:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    if best_summary is None:
        best_summary = {"verdict": "manual", "reason": "no rollouts executed"}

    best_summary["mcts"] = {
        "rollouts": len(rollouts),
        "bestScore": round(best_score, 4),
        "params": asdict(params),
    }

    return best_summary
