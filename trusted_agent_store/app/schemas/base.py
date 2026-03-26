from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    COMPANY = "company"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class SubmissionState(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AutoDecision(str, Enum):
    AUTO_APPROVED = "auto_approved"
    AUTO_REJECTED = "auto_rejected"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    role: UserRole
    organization_id: Optional[str] = None


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Submission Schemas ---
class SubmissionBase(BaseModel):
    agent_id: str
    card_document: Dict[str, Any]
    endpoint_manifest: Dict[str, Any]
    endpoint_snapshot_hash: str
    signature_bundle: Dict[str, Any]
    organization_meta: Dict[str, Any]
    request_context: Optional[Dict[str, Any]] = None


class SubmissionCreate(BaseModel):
    agent_id: Optional[str] = None  # Will be extracted from Agent Card
    agent_card_url: str
    endpoint_manifest: Optional[Dict[str, Any]] = {}
    endpoint_snapshot_hash: Optional[str] = "hash"
    signature_bundle: Optional[Dict[str, Any]] = {}
    organization_meta: Optional[Dict[str, Any]] = {}
    request_context: Optional[Dict[str, Any]] = None


class Submission(SubmissionBase):
    id: str
    state: str
    manifest_warnings: List[str] = []

    trust_score: int
    score_breakdown: Dict[str, Any]
    auto_decision: Optional[AutoDecision] = None

    organization_id: Optional[str] = None
    submitted_by: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Review Schemas ---
class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewRequest(BaseModel):
    action: ReviewAction
    reason: str
    notes: Optional[str] = None


class TrustScoreUpdate(BaseModel):
    trust_score: Optional[int] = None
    reasoning: Optional[Dict[str, str]] = None


# --- Publish Schemas ---
class PublishRequest(BaseModel):
    override: bool = Field(default=False, description="Override state validation and force publish")
    reason: Optional[str] = Field(default=None, description="Reason for manual publish (required for override)")


class PublishResponse(BaseModel):
    status: str
    message: str
    agent_id: Optional[str] = None
    published_at: Optional[str] = None

