from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import uuid
import enum

def generate_uuid():
    return str(uuid.uuid4())

class UserRole(str, enum.Enum):
    COMPANY = "company"
    REVIEWER = "reviewer"
    ADMIN = "admin"

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    website = Column(String)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users = relationship("User", back_populates="organization")
    submissions = relationship("Submission", back_populates="organization")

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # Enum: company, reviewer, admin
    organization_id = Column(String, ForeignKey("organizations.id"))
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True))

    organization = relationship("Organization", back_populates="users")
    submissions = relationship("Submission", back_populates="submitter")

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_id = Column(String, nullable=False, index=True)
    card_document = Column(JSON, nullable=False)
    endpoint_manifest = Column(JSON, nullable=False)
    endpoint_snapshot_hash = Column(String, nullable=False)
    signature_bundle = Column(JSON, nullable=False)
    organization_meta = Column(JSON, nullable=False)
    state = Column(String, nullable=False, index=True)
    manifest_warnings = Column(JSON, default=[])
    request_context = Column(JSON)

    # Trust Score
    trust_score = Column(Integer, default=0, index=True)
    score_breakdown = Column(JSON, default={})
    auto_decision = Column(String, index=True) # auto_approved, auto_rejected, requires_human_review

    # Relations
    organization_id = Column(String, ForeignKey("organizations.id"))
    submitted_by = Column(String, ForeignKey("users.id"))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization = relationship("Organization", back_populates="submissions")
    submitter = relationship("User", back_populates="submissions")
    trust_score_history = relationship("TrustScoreHistory", back_populates="submission")

class AgentEndpointSnapshot(Base):
    __tablename__ = "agent_endpoint_snapshots"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_id = Column(String, nullable=False, index=True)
    relay_id = Column(String, unique=True)
    manifest = Column(JSON, nullable=False)
    snapshot_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class TrustScoreHistory(Base):
    __tablename__ = "trust_score_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=False)
    agent_id = Column(String) # Optional in some schemas, but good to have

    # From 20251115_governance.sql
    total_score = Column(Integer, nullable=False)
    security_score = Column(Integer)
    functional_score = Column(Integer)
    judge_score = Column(Integer)
    implementation_score = Column(Integer)
    auto_decision = Column(String)
    reasoning = Column(JSON, default={})

    # From 20251114_trust_scores.sql (merged concept)
    previous_score = Column(Integer)
    score_change = Column(Integer)
    change_reason = Column(Text)
    stage = Column(String)
    triggered_by = Column(String) # system, human, incident, re_evaluation
    metadata_ = Column("metadata", JSON, default={}) # metadata is reserved in SQLAlchemy sometimes

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    submission = relationship("Submission", back_populates="trust_score_history")

class GovernancePolicy(Base):
    __tablename__ = "governance_policies"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_type = Column(String, nullable=False) # aisi_prompt, security_threshold, etc.
    version = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    activated_at = Column(DateTime(timezone=True))

class TrustSignal(Base):
    __tablename__ = "trust_signals"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_id = Column(String, nullable=False, index=True)
    signal_type = Column(String, nullable=False) # security_incident, functional_error, etc.
    severity = Column(String, nullable=False) # critical, high, medium, low, info
    description = Column(Text)
    metadata_ = Column("metadata", JSON, default={})
    reporter_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(DateTime(timezone=True))
    resolution_notes = Column(Text)
