"""Imports every model so Base.metadata is complete (Alembic and tests use this)."""

from app.accounts.models import (
    Account,
    AccountDomain,
    AccountDuplicateDismissal,
    AccountIdentifier,
    Contact,
    Suppression,
)
from app.audit.models import AuditLog
from app.auth.models import Invite, Permission, Role, User, UserSession
from app.briefs.models import LeadBrief
from app.catalogue.models import ReferenceProject, Service, ServiceMatch
from app.clients.models import (
    ClientFeedback,
    ClientHealthSnapshot,
    ExpansionOpportunity,
    Milestone,
    Project,
    ProjectRisk,
    Referral,
)
from app.core.models import Base
from app.crm.models import Activity, Lead, Opportunity, Task, TimelineEvent
from app.deals.models import Deal, DealStageChange, Pipeline, PipelineStage
from app.discovery.models import DiscoveredCompany, DiscoveryJob
from app.documents.models import Document
from app.evidence.models import Claim, Evidence, Observation
from app.learning.models import DealOutcome, LearnedProposal, SalesFeedback
from app.mail.models import EmailMessage, Mailbox
from app.monitoring.models import MonitorAlert, Watch
from app.opportunities.models import OpportunityCandidate, OpportunityCategory
from app.outreach.models import Enrollment, EnrollmentStep, OutreachTemplate, Sequence, SequenceStep
from app.qualification.models import IcpConfig, QualificationResult
from app.reports.models import SavedView
from app.research.models import RawResponse, ResearchPage, ResearchRun, ResearchStage
from app.scoring.models import ScoreSnapshot, ScoringConfig
from app.similarity.models import SimilarityResult

__all__ = [
    "Account",
    "AccountDomain",
    "AccountDuplicateDismissal",
    "AccountIdentifier",
    "Activity",
    "AuditLog",
    "Base",
    "Claim",
    "ClientFeedback",
    "ClientHealthSnapshot",
    "Contact",
    "Deal",
    "DealOutcome",
    "DealStageChange",
    "DiscoveredCompany",
    "DiscoveryJob",
    "Document",
    "EmailMessage",
    "Enrollment",
    "EnrollmentStep",
    "Evidence",
    "ExpansionOpportunity",
    "IcpConfig",
    "Invite",
    "Lead",
    "LeadBrief",
    "LearnedProposal",
    "Mailbox",
    "Milestone",
    "MonitorAlert",
    "Observation",
    "Opportunity",
    "OpportunityCandidate",
    "OpportunityCategory",
    "OutreachTemplate",
    "Permission",
    "Pipeline",
    "PipelineStage",
    "Project",
    "ProjectRisk",
    "QualificationResult",
    "RawResponse",
    "ReferenceProject",
    "Referral",
    "ResearchPage",
    "ResearchRun",
    "ResearchStage",
    "Role",
    "SalesFeedback",
    "SavedView",
    "ScoreSnapshot",
    "ScoringConfig",
    "Sequence",
    "SequenceStep",
    "Service",
    "ServiceMatch",
    "SimilarityResult",
    "Suppression",
    "Task",
    "TimelineEvent",
    "User",
    "UserSession",
    "Watch",
]
