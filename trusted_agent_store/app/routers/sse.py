"""
SSE router for real-time jury judge updates.
"""

import asyncio
import json
import logging
import threading
from typing import Dict, List, Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Submission

logger = logging.getLogger(__name__)

router = APIRouter()


class SSEManager:
    """Simple per-submission SSE fan-out using asyncio.Queue."""

    def __init__(self) -> None:
        # submission_id -> list of queues
        self._connections: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread_lock = threading.Lock()

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the main event loop for thread-safe operations."""
        with self._thread_lock:
            self._main_loop = loop

    def send_sync(self, submission_id: str, data: dict) -> None:
        """
        Thread-safe synchronous send for use from background threads.
        This schedules the send on the main event loop.
        """
        event_type = data.get("type", "unknown")
        print(f"[SSE Manager] send_sync() called: type={event_type}, submission={submission_id[:8]}...")

        with self._thread_lock:
            loop = self._main_loop

        if loop is None:
            print(f"[SSE Manager] ❌ Main loop not set, cannot send SSE message")
            logger.warning("Main loop not set, cannot send SSE message")
            return

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.send(submission_id, data), loop
            )
            # Wait for completion with timeout
            future.result(timeout=5.0)
            print(f"[SSE Manager] ✅ send_sync completed: type={event_type}")
        except Exception as e:
            print(f"[SSE Manager] ❌ Failed to send SSE message: {e}")
            logger.error(f"Failed to send SSE message: {e}")

    async def connect(self, submission_id: str) -> asyncio.Queue:
        """Register a new subscriber and return its queue."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._connections.setdefault(submission_id, []).append(queue)
        total = len(self._connections.get(submission_id, []))
        print(f"[SSE Manager] 🔌 Client connected: submission={submission_id[:8]}..., total_clients={total}")
        logger.info(f"SSE connected for submission {submission_id} (total={total})")
        return queue

    async def disconnect(self, submission_id: str, queue: asyncio.Queue) -> None:
        """Remove subscriber queue."""
        async with self._lock:
            if submission_id in self._connections:
                try:
                    self._connections[submission_id].remove(queue)
                    if not self._connections[submission_id]:
                        del self._connections[submission_id]
                except ValueError:
                    pass
        logger.info(f"SSE disconnected for submission {submission_id}")

    async def send(self, submission_id: str, data: dict) -> None:
        """Send data to all subscribers of a submission."""
        event_type = data.get("type", "unknown")
        async with self._lock:
            queues = list(self._connections.get(submission_id, []))

        # Debug log: always print connection status
        print(f"[SSE Manager] send() called: type={event_type}, submission={submission_id[:8]}..., connected_clients={len(queues)}")

        if not queues:
            print(f"[SSE Manager] ⚠️ No clients connected for {submission_id[:8]}..., message dropped")
            return

        payload = json.dumps(data, ensure_ascii=False)
        for q in queues:
            # Non-blocking put: drop if queue is full (should not block streaming loop)
            try:
                q.put_nowait(payload)
                print(f"[SSE Manager] ✅ Message queued: type={event_type}")
            except asyncio.QueueFull:
                logger.warning("SSE queue full; dropping message")
                print(f"[SSE Manager] ❌ Queue full, message dropped: type={event_type}")


manager = SSEManager()


def get_sse_manager() -> SSEManager:
    return manager


def get_initial_state_events(submission: Submission) -> list:
    """
    Generate initial state events from submission's current state.
    This allows clients connecting mid-evaluation to receive past events.
    """
    events = []

    if not submission or not submission.score_breakdown:
        return events

    sb = submission.score_breakdown

    # Send W&B info if available
    if sb.get("wandb"):
        events.append({
            "type": "initial_state",
            "category": "wandb",
            "data": sb["wandb"]
        })

    # Send judge summary if available (includes phase1 evaluations)
    judge_summary = sb.get("judge_summary")
    if judge_summary and judge_summary.get("scenarios"):
        for scenario in judge_summary["scenarios"]:
            # 陪審員ごとの評価（3行）
            if scenario.get("type") == "juror_evaluation":
                events.append({
                    "type": "juror_evaluation",
                    "phase": "collective_independent",
                    "juror": scenario.get("jurorId"),
                    "verdict": scenario.get("verdict"),
                    "score": scenario.get("overallScore"),
                    "rationale": scenario.get("rationale"),
                    "taskCompletion": scenario.get("taskCompletion"),
                    "toolUsage": scenario.get("toolUsage"),
                    "autonomy": scenario.get("autonomy"),
                    "safety": scenario.get("safety"),
                    "isReplay": True
                })

            # 裁判官の最終判定（1行）
            elif scenario.get("type") == "final_judgment":
                events.append({
                    "type": "final_judgment",
                    "finalVerdict": scenario.get("finalVerdict"),
                    "finalScore": scenario.get("finalScore"),
                    "confidence": scenario.get("confidence"),
                    "rationale": scenario.get("rationale") or scenario.get("finalJudgeRationale"),
                    "isReplay": True
                })

    return events


@router.get("/sse/submissions/{submission_id}/judge")
async def sse_judge_stream(request: Request, submission_id: str, db: Session = Depends(get_db)):
    """
    SSE endpoint for Jury Judge real-time updates.
    Sends initial state on connection, then streams real-time updates.
    """
    # Get current submission state for initial events
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    initial_events = get_initial_state_events(submission) if submission else []

    queue = await manager.connect(submission_id)

    async def event_generator():
        try:
            # Send initial state events first
            for event in initial_events:
                payload = json.dumps(event, ensure_ascii=False)
                print(f"[SSE Manager] 📤 Sending initial event: type={event.get('type')}")
                yield f"data: {payload}\n\n"

            while True:
                # Abort if client disconnects
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield "event: ping\ndata: {}\n\n"
        finally:
            await manager.disconnect(submission_id, queue)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        "Connection": "keep-alive",
    }

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
