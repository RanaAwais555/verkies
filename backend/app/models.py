"""Imports every model so Base.metadata is complete (Alembic and tests use this)."""

from app.accounts.models import Account, AccountDomain, AccountIdentifier, Contact, Suppression
from app.audit.models import AuditLog
from app.auth.models import Invite, Permission, Role, User, UserSession
from app.briefs.models import LeadBrief
from app.catalogue.models import ReferenceProject, Service, ServiceMatch
from app.core.models import Base
from app.crm.models import Activity, Lead, Opportunity, Task, TimelineEvent
from app.evidence.models import Claim, Evidence
from app.opportunities.models import OpportunityCandidate, OpportunityCategory
from app.qualification.models import IcpConfig, QualificationResult
from app.research.models import RawResponse, ResearchPage, ResearchRun, ResearchStage
from app.scoring.models import ScoreSnapshot, ScoringConfig
from app.similarity.models import SimilarityResult

__all__ = [
    "Account",
    "AccountDomain",
    "AccountIdentifier",
    "Activity",
    "AuditLog",
    "Base",
    "Claim",
    "Contact",
    "Evidence",
    "IcpConfig",
    "Invite",
    "Lead",
    "LeadBrief",
    "Opportunity",
    "OpportunityCandidate",
    "OpportunityCategory",
    "Permission",
    "QualificationResult",
    "RawResponse",
    "ReferenceProject",
    "ResearchPage",
    "ResearchRun",
    "ResearchStage",
    "Role",
    "ScoreSnapshot",
    "ScoringConfig",
    "Service",
    "ServiceMatch",
    "SimilarityResult",
    "Suppression",
    "Task",
    "TimelineEvent",
    "User",
    "UserSession",
]
