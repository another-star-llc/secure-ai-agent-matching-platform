from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, schemas
from ..database import get_db
import uuid

router = APIRouter(
    prefix="/api/reviews",
    tags=["reviews"],
)

@router.post("/{submission_id}/decision", response_model=schemas.Submission)
def submit_review_decision(
    submission_id: str,
    review: schemas.ReviewRequest,
    db: Session = Depends(get_db)
):
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    if review.action == schemas.ReviewAction.APPROVE:
        submission.state = "approved"

        # Update score_breakdown to mark human review as completed
        current_breakdown = dict(submission.score_breakdown or {})
        if "stages" not in current_breakdown:
            current_breakdown["stages"] = {}
        current_breakdown["stages"]["human"] = {
            "status": "completed",
            "attempts": 1,
            "message": "Human review approved",
            "warnings": []
        }

        # Auto-publish approved agents
        from .submissions import publish_agent
        publish_result = publish_agent(submission)

        if publish_result["status"] == "published":
            submission.state = "published"

            # Mark publish stage as completed
            current_breakdown["stages"]["publish"] = {
                "status": "completed",
                "attempts": 1,
                "message": "Agent published to registry",
                "warnings": []
            }

            # Record publish info in score_breakdown
            current_breakdown["publish_summary"] = publish_result
            current_breakdown["auto_publish"] = {
                "published_at": publish_result["publishedAt"],
                "triggered_by": "approval",
                "reviewer_reason": review.reason
            }
            submission.score_breakdown = current_breakdown
            submission.updated_at = datetime.utcnow()
        else:
            # If publish fails, log the error but keep approved state
            current_breakdown["stages"]["publish"] = {
                "status": "failed",
                "attempts": 1,
                "message": f"Publish failed: {publish_result.get('error', 'Unknown error')}",
                "warnings": []
            }
            current_breakdown["publish_error"] = {
                "error": publish_result.get("error", "Unknown error"),
                "failed_at": datetime.utcnow().isoformat()
            }
            submission.score_breakdown = current_breakdown

    elif review.action == schemas.ReviewAction.REJECT:
        submission.state = "rejected"

        # Update score_breakdown to mark human review as completed with rejection
        current_breakdown = dict(submission.score_breakdown or {})
        if "stages" not in current_breakdown:
            current_breakdown["stages"] = {}
        current_breakdown["stages"]["human"] = {
            "status": "completed",
            "attempts": 1,
            "message": "Human review rejected",
            "warnings": []
        }
        # Mark publish stage as failed due to manual rejection
        current_breakdown["stages"]["publish"] = {
            "status": "failed",
            "attempts": 1,
            "message": "Rejected by human reviewer",
            "warnings": []
        }
        submission.score_breakdown = current_breakdown

    # Log the decision (simplified logic)
    # In a real app, we would create a TrustScoreHistory entry here

    db.commit()
    db.refresh(submission)
    return submission

@router.post("/{submission_id}/score", response_model=schemas.Submission)
def update_trust_score(
    submission_id: str,
    score_update: schemas.TrustScoreUpdate,
    db: Session = Depends(get_db)
):
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    if score_update.trust_score is not None:
        submission.trust_score = score_update.trust_score

    if score_update.reasoning:
        submission.score_breakdown = score_update.reasoning

    db.commit()
    db.refresh(submission)
    return submission

@router.post("/{submission_id}/publish", response_model=schemas.PublishResponse)
def publish_submission(
    submission_id: str,
    publish_request: schemas.PublishRequest,
    db: Session = Depends(get_db)
):
    """
    手動でSubmissionをAgentRegistryに公開する

    - override=False: state='approved'のみ公開可能
    - override=True: どのstateでも公開可能（管理者判断）
    """
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    # override=Falseの場合はapproved状態のみ許可
    if not publish_request.override and submission.state not in ["approved", "published"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot publish submission in state '{submission.state}'. Set override=true to force publish."
        )

    # override=Trueの場合は理由を必須に
    if publish_request.override and not publish_request.reason:
        raise HTTPException(
            status_code=400,
            detail="Reason is required when using override=true"
        )

    # publish_agent実行
    from .submissions import publish_agent
    publish_result = publish_agent(submission)

    if publish_result["status"] == "published":
        # submissionのstateを更新
        submission.state = "published"

        # score_breakdownに記録
        current_breakdown = dict(submission.score_breakdown or {})
        if "stages" not in current_breakdown:
            current_breakdown["stages"] = {}

        # Mark human and publish stages as completed
        current_breakdown["stages"]["human"] = {
            "status": "completed",
            "attempts": 1,
            "message": "Manual override publish",
            "warnings": []
        }
        current_breakdown["stages"]["publish"] = {
            "status": "completed",
            "attempts": 1,
            "message": "Agent published via override",
            "warnings": []
        }

        current_breakdown["publish_summary"] = publish_result
        current_breakdown["manual_publish"] = {
            "published_at": publish_result["publishedAt"],
            "override": publish_request.override,
            "reason": publish_request.reason,
            "published_by": "admin"  # 将来: current_user.id
        }
        submission.score_breakdown = current_breakdown
        submission.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(submission)

        return schemas.PublishResponse(
            status="success",
            message="Agent published successfully to registry",
            agent_id=submission.agent_id,
            published_at=publish_result["publishedAt"]
        )
    else:
        # Mark publish stage as failed
        current_breakdown = dict(submission.score_breakdown or {})
        if "stages" not in current_breakdown:
            current_breakdown["stages"] = {}
        current_breakdown["stages"]["publish"] = {
            "status": "failed",
            "attempts": 1,
            "message": f"Publish failed: {publish_result.get('error', 'Unknown error')}",
            "warnings": []
        }
        submission.score_breakdown = current_breakdown
        db.commit()

        raise HTTPException(
            status_code=500,
            detail=f"Publish failed: {publish_result.get('error', 'Unknown error')}"
        )
