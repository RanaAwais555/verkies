"""Enumerations shared across modules. Stored as text with CHECK constraints (see core.models)."""

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ResearchStageName(StrEnum):
    VALIDATE = "validate"
    CRAWL = "crawl"
    EXTRACT = "extract"
    DETECT = "detect"
    QUALIFY = "qualify"
    SCORE = "score"
    MATCH = "match"
    BRIEF = "brief"


class RejectionReason(StrEnum):
    """Master context §3."""

    NO_COMMERCIAL_OPPORTUNITY = "no_commercial_opportunity"
    WRONG_ICP = "wrong_icp"
    INACTIVE_COMPANY = "inactive_company"
    DUPLICATE = "duplicate"
    COMPETITOR = "competitor"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_RELEVANT_SERVICE = "no_relevant_service"
    NO_REACHABLE_BUYER = "no_reachable_buyer"
    HOBBY_OR_PERSONAL = "hobby_or_personal"
    STUDENT_OR_FREELANCER = "student_or_freelancer"
    UNSUITABLE_COMPANY_SIZE = "unsuitable_company_size"
    IRRELEVANT_INDUSTRY = "irrelevant_industry"
    EXISTING_SOLUTION_SUFFICIENT = "existing_solution_sufficient"
    SUPPRESSED_ACCOUNT = "suppressed_account"


class AccountType(StrEnum):
    """Lifecycle state plus the other account types (§6)."""

    PROSPECT = "prospect"
    QUALIFIED_PROSPECT = "qualified_prospect"
    OPPORTUNITY = "opportunity"
    CUSTOMER = "customer"
    FORMER_CUSTOMER = "former_customer"
    PARTNER = "partner"
    COMPETITOR = "competitor"
    SUPPRESSED = "suppressed"


class AgencyClass(StrEnum):
    COMPETITOR = "competitor"
    POTENTIAL_PARTNER = "potential_partner"
    REFERRAL_PARTNER = "referral_partner"
    WHITE_LABEL_PARTNER = "white_label_partner"
    SUBCONTRACTING = "subcontracting"


class PriorityBand(StrEnum):
    """SCORING_SPEC.md §6."""

    HOT = "hot"
    HIGH = "high"
    QUALIFIED = "qualified"
    MONITOR = "monitor"
    REJECT = "reject"


class EvidenceType(StrEnum):
    PAGE_CONTENT = "page_content"
    HTTP_HEADER = "http_header"
    DNS_RECORD = "dns_record"
    STRUCTURED_DATA = "structured_data"
    TECHNOLOGY_FINGERPRINT = "technology_fingerprint"
    JOB_POSTING = "job_posting"
    COMPANY_REGISTRY = "company_registry"
    NEWS_ITEM = "news_item"
    USER_NOTE = "user_note"
    OTHER = "other"


class ClaimClass(StrEnum):
    """AI_SPEC.md §2."""

    FACT = "fact"
    INFERENCE = "inference"
    RECOMMENDATION = "recommendation"


class DecisionMakerRole(StrEnum):
    ECONOMIC_BUYER = "economic_buyer"
    DECISION_MAKER = "decision_maker"
    TECHNICAL_BUYER = "technical_buyer"
    PRODUCT_BUYER = "product_buyer"
    MARKETING_BUYER = "marketing_buyer"
    OPERATIONS_BUYER = "operations_buyer"
    CHAMPION = "champion"
    INFLUENCER = "influencer"
    USER = "user"
    PROCUREMENT = "procurement"
    BLOCKER = "blocker"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class LinkedInConnectionStatus(StrEnum):
    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    CONNECTED = "connected"


class SuppressionKind(StrEnum):
    EMAIL = "email"
    DOMAIN = "domain"
    ACCOUNT = "account"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    RESEARCHING = "researching"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    REJECTED = "rejected"
    NURTURE = "nurture"
    CONVERTED = "converted"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ActivityChannel(StrEnum):
    EMAIL = "email"
    CALL = "call"
    LINKEDIN = "linkedin"
    MEETING = "meeting"
    WHATSAPP = "whatsapp"
    MANUAL = "manual"
    SYSTEM = "system"


class ServiceSlot(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    EXPANSION = "expansion"


class BriefMode(StrEnum):
    TEMPLATE = "template"
    AI = "ai"


class AuditSource(StrEnum):
    UI = "ui"
    API = "api"
    WORKER = "worker"
    IMPORT = "import"
    CLI = "cli"
    SYSTEM = "system"
