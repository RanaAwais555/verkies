// Shapes returned by the VROS API (/api/v1). Null scores mean Unknown, never zero.

export type User = {
  id: string;
  email: string;
  name: string;
  roles: string[];
  permissions: string[];
  is_active: boolean;
  last_login_at: string | null;
};

export type Session = { user: User; csrf_token: string };

export type Stage = {
  stage: string;
  status: string;
  progress_pct: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  detail: Record<string, unknown>;
};

export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "retrying";
export type ReviewStatus = "pending" | "approved" | "rejected";

export type Run = {
  id: string;
  input_url: string;
  normalised_domain: string;
  status: RunStatus;
  review_status: ReviewStatus;
  requested_by_id: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  retry_count: number;
  possible_duplicate_of: string[];
  account_id: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
  progress_pct: number;
  stages: Stage[];
};

export type Page = {
  kind: string;
  url: string;
  final_url: string | null;
  discovered_via: string;
  category: string | null;
  status_code: number | null;
  content_type: string | null;
  bytes: number;
  from_cache: boolean;
  rendered: boolean;
  title: string | null;
  skip_reason: string | null;
  error: string | null;
};

export type RunDetail = Run & { pages: Page[] };

export type Evidence = {
  id: string;
  source_url: string;
  evidence_type: string;
  excerpt: string;
  collected_at: string;
  confidence: number;
};

export type Observation = {
  id: string;
  area: string;
  key: string;
  value: unknown;
  confidence: number;
  seen_on: string[];
  evidence: Evidence;
};

export type Intelligence = { run_id: string; attempt: number; areas: Record<string, Observation[]> };

export type DetectedOpportunity = {
  id: string;
  category: string;
  title: string;
  problem: string;
  confidence: number;
  rule_key: string;
  evidence: Evidence[];
};

export type Assessment = {
  run_id: string;
  opportunities: DetectedOpportunity[];
  qualification: {
    icp_fit: number | null;
    hard_reject: boolean;
    rejection_reason: string | null;
    explanation: string;
    components: Record<string, unknown>[];
    negative_icp_hits: Record<string, unknown>[];
  } | null;
  score: {
    scores: Record<string, number | null>;
    priority_score: number | null;
    priority_band: string | null;
    qualifies: boolean;
    not_qualified_because: string[];
    breakdown: Record<string, unknown>;
    created_at: string;
  } | null;
};

export type ClaimClass = "fact" | "inference" | "recommendation";

export type BriefClaim = {
  claim_id: string;
  claim_class: ClaimClass;
  text: string;
  evidence: Evidence[];
};

export type BriefSection = {
  source: "template" | "ai";
  claims: BriefClaim[];
  unknown: string | null;
  notes: string[];
};

export type Brief = {
  run_id: string;
  mode: "template" | "ai";
  generated_at: string;
  generated_by: Record<string, unknown>;
  summary: {
    company: string | null;
    domain: string;
    priority_score: number | null;
    priority_band: string | null;
    qualifies: boolean;
  } & Record<string, unknown>;
  sections: Record<string, BriefSection>;
};

export type Duplicate = {
  account_id: string;
  name: string;
  primary_domain: string | null;
  match: string; // domain, name, flagged or identifier:<scheme>
  similarity?: number | null;
};

export type QueueItem = {
  run_id: string;
  domain: string;
  input_url: string;
  company: string | null;
  priority_score: number | null;
  priority_band: string | null;
  qualifies: boolean;
  hard_reject: boolean;
  recommended_rejection: string | null;
  explanation: string;
  next_action: string | null;
  scores: Record<string, number | null>;
  possible_duplicates: Duplicate[];
  requested_by_id: string;
  finished_at: string | null;
};

export type Approval = {
  run_id: string;
  account_id: string;
  created_account: boolean;
  lead_id: string;
  opportunity_id: string | null;
  task_id: string;
  task_due_at: string | null;
  contact_ids: string[];
};

export type Owner = { id: string; name: string };

export type Task = {
  id: string;
  account_id: string;
  account_name: string | null;
  lead_id: string | null;
  opportunity_id: string | null;
  title: string;
  description: string | null;
  owner_id: string | null;
  owner_name: string | null;
  due_at: string | null;
  priority: "low" | "normal" | "high" | "urgent";
  status: "open" | "in_progress" | "done" | "cancelled";
  completed_at: string | null;
  created_at: string;
};

export type Opportunity = {
  id: string;
  account_id: string;
  account_name: string | null;
  lead_id: string | null;
  name: string;
  problem: string;
  category_name: string | null;
  service_name: string | null;
  stage: string;
  owner_id: string | null;
  estimated_value: number | null;
  probability: number | null;
  next_action_task_id: string | null;
  requires_attention: string[];
  created_at: string;
};

export type AccountSummary = {
  id: string;
  name: string;
  primary_domain: string | null;
  account_type: string;
  industry: string | null;
  hq_country: string | null;
  owner: Owner | null;
  priority_score: number | null;
  priority_band: string | null;
  next_activity_at: string | null;
  last_activity_at: string | null;
  open_tasks: number;
  created_at: string;
};

/** Relationship tracking (§12), computed by the API from logged activities. */
export type Relationship = {
  first_interaction_at: string | null;
  latest_interaction_at: string | null;
  days_since_contact: number | null;
  interactions: number;
  last_reply_at: string | null;
  attempts_since_reply: number;
  response_status: "not_contacted" | "no_reply" | "awaiting_reply" | "replied";
};

export type Contact = {
  id: string;
  name: string;
  title: string | null;
  department: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  notes: string | null;
  decision_maker_role: string | null;
  verification_status: string;
  source: string;
  source_url: string | null;
  collected_at: string;
  confidence: number;
  relationship: Relationship | null;
};

export const DECISION_MAKER_ROLES = [
  "economic_buyer",
  "decision_maker",
  "technical_buyer",
  "product_buyer",
  "marketing_buyer",
  "operations_buyer",
  "champion",
  "influencer",
  "user",
  "procurement",
] as const;

export type ActivityKind = "call" | "meeting" | "note" | "message";

export type Activity = {
  id: string;
  account_id: string;
  account_name: string;
  kind: ActivityKind;
  channel: string;
  direction: "outbound" | "inbound" | "conversation" | "internal";
  call_outcome: "connected" | "no_answer" | "voicemail" | null;
  occurred_at: string;
  summary: string;
  contact: { id: string; name: string | null } | null;
  opportunity_id: string | null;
  deal_id: string | null;
  logged_by: { id: string; name: string | null } | null;
  created_at: string;
};

export type FollowUpKind = "overdue_follow_up" | "no_next_action" | "stale_opportunity" | "inactive_deal";

export type FollowUpFlag = {
  kind: FollowUpKind;
  account_id: string;
  account_name: string;
  ref_table: string;
  ref_id: string;
  title: string;
  detail: string;
  since: string | null;
  owner: { id: string; name: string | null } | null;
};

export type FollowUps = {
  flags: FollowUpFlag[];
  counts: Record<FollowUpKind, number>;
  stale_opportunity_days: number;
  inactive_deal_days: number;
};

export type Lead = {
  id: string;
  research_run_id: string | null;
  source: string;
  status: string;
  owner: Owner | null;
  priority_score: number | null;
  priority_band: string | null;
  qualified_at: string | null;
  created_at: string;
};

export type Account360 = AccountSummary & {
  legal_name: string | null;
  website_url: string | null;
  description: string | null;
  hq_city: string | null;
  company_size_band: string | null;
  source: string | null;
  linkedin_company_url: string | null;
  domains: string[];
  scores: Record<string, number | null>;
  leads: Lead[];
  opportunities: Opportunity[];
  contacts: Contact[];
  tasks: Task[];
  research_runs: Pick<Run, "id" | "normalised_domain" | "status" | "review_status" | "created_at" | "finished_at">[];
  latest_brief_run_id: string | null;
  relationship: Relationship;
};

export type TimelineEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  summary: string;
  ref_table: string | null;
  ref_id: string | null;
  actor: Owner | null;
};

export type AuditEntry = {
  id: string;
  occurred_at: string;
  user_id: string | null;
  object_table: string;
  object_id: string | null;
  action: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  source: string;
  reason: string | null;
};

export type TeamMember = { id: string; name: string; email: string };

export type Service = {
  id: string;
  key: string;
  name: string;
  description: string;
  solves: string[];
  confirmed: boolean;
  is_active: boolean;
  source_url: string | null;
};

export type ReferenceProject = {
  id: string;
  name: string;
  industry: string | null;
  business_model: string | null;
  problem: string | null;
  technologies: string[];
  growth_stage: string | null;
  buyer_type: string | null;
  workflow_notes: string | null;
  status: string | null;
  website_url: string | null;
  source_url: string | null;
  services: string[];
  profile_complete: boolean;
};

export type Role = { key: string; name: string; permissions: string[] };

export type Invite = {
  id: string;
  email: string;
  roles: string[];
  expires_at: string;
  created_at: string;
  invite_url?: string;
};

export type ConfigVersion = {
  kind: "icp" | "scoring";
  version: number;
  is_active: boolean;
  note: string | null;
  created_at: string;
  config: Record<string, unknown>;
};

export type ProviderStatus = { name: string; status: "ok" | "degraded" | "off"; detail: string };

export type Readiness = { status: string; checks: Record<string, { status: string; error: string | null }> };

export const REJECTION_REASONS: Record<string, string> = {
  no_commercial_opportunity: "No commercial opportunity",
  wrong_icp: "Wrong ICP",
  inactive_company: "Inactive company",
  duplicate: "Duplicate",
  competitor: "Competitor",
  insufficient_evidence: "Insufficient evidence",
  no_relevant_service: "No relevant service",
  no_reachable_buyer: "No reachable buyer",
  hobby_or_personal: "Hobby or personal",
  student_or_freelancer: "Student or freelancer",
  unsuitable_company_size: "Unsuitable company size",
  irrelevant_industry: "Irrelevant industry",
  existing_solution_sufficient: "Existing solution sufficient",
  suppressed_account: "Suppressed account",
};

export type ImportRowStatus =
  | "pending"
  | "new"
  | "invalid"
  | "duplicate_in_file"
  | "existing_account"
  | "possible_duplicate"
  | "already_researched"
  | "suppressed"
  | "queued"
  | "finding_website"
  | "no_website";

export type ImportRow = {
  id: string;
  row_number: number;
  raw: Record<string, string>;
  name: string | null;
  website_url: string | null;
  normalised_domain: string | null;
  country: string | null;
  industry: string | null;
  notes: string | null;
  status: ImportRowStatus;
  status_detail: string | null;
  matched_account_id: string | null;
  research_run_id: string | null;
  run_status: string | null;
  run_review_status: string | null;
};

export type ImportJob = {
  id: string;
  name: string;
  kind: string;
  status: "uploaded" | "checked" | "running";
  columns: string[];
  mapping: Record<string, string>;
  row_count: number;
  stats: Record<string, number>;
  created_by_id: string;
  created_at: string;
};

export type ImportDetail = ImportJob & { fields: string[]; rows: ImportRow[] };

export type BulkResearchResult = { started: string[]; skipped: Record<string, string>; queue_failures: number };

// Slice 2.6: ranked leads with reasons, plain-English search, duplicates and merge.
export type RankReason = { kind: "score" | "gate" | "unknown" | "signal" | "opportunity"; text: string; source_url: string | null };

export type RankedLead = { rank: number; account: AccountSummary; reasons: RankReason[]; scored_at: string | null };

export type Understood = { phrase: string; meaning: string };

export type LeadSearch = {
  query: string;
  interpretation: { understood: Understood[]; unsupported: Understood[]; top_leads: boolean; limit: number };
  results: RankedLead[];
};

export type DuplicatePair = { account_a: AccountSummary; account_b: AccountSummary; reasons: string[]; similarity: number | null };

export type MergeResult = { account_id: string; retired_id: string; moved: Record<string, number>; filled: string[] };

// Slice 3.1: pipelines, deals and the forecast. A null value or probability is Unknown, never 0.
export type StageOutcome = "open" | "won" | "lost" | "nurture" | "inactive";

export type PipelineStage = { id: string; key: string; name: string; position: number; probability: number | null; outcome: StageOutcome };

export type Pipeline = { id: string; key: string; name: string; kind: string; stages: PipelineStage[] };

export type Pipelines = { pipelines: Pipeline[]; lost_reasons: { key: string; label: string }[] };

export type Deal = {
  id: string;
  name: string;
  account_id: string;
  account_name: string;
  account_domain: string | null;
  priority_band: string | null;
  opportunity_id: string | null;
  opportunity_name: string | null;
  pipeline_id: string;
  pipeline_key: string;
  stage_id: string;
  stage_key: string;
  stage_name: string;
  outcome: StageOutcome;
  value: number | null;
  currency: string;
  probability: number | null;
  probability_is_stage_default: boolean;
  weighted_value: number | null;
  expected_close: string | null;
  owner: { id: string; name: string | null } | null;
  next_task: { id: string; title: string; due_at: string | null; owner_name: string | null } | null;
  last_activity_at: string | null;
  stage_entered_at: string;
  days_in_stage: number;
  closed_at: string | null;
  lost_reason: string | null;
  lost_note: string | null;
  requires_attention: string[];
  created_at: string;
};

export type Forecast = {
  currency: string;
  open_count: number;
  open_value: number;
  unknown_value_count: number;
  weighted_value: number;
  unweighted_count: number;
  no_close_date_count: number;
  won_count: number;
  won_value: number;
  won_unknown_value_count: number;
  lost_count: number;
  lost_value: number;
  lost_unknown_value_count: number;
  months: { month: string; count: number; value: number; weighted: number }[];
};

// --- reporting (slice 3.3) ---

export type ReportPeriod = "7d" | "30d" | "90d" | "365d" | "ytd";

export type ReportMoney = { amount: number; currency: string };

/** One figure on a dashboard. `value` null is Unknown; `definition` says exactly how it is counted. */
export type ReportFigure = {
  key: string;
  label: string;
  value: number | null;
  unit: "count" | "percent" | "days" | "money" | "score";
  definition: string;
  currency: string | null;
  detail: string | null;
  href: string | null;
};

export type ReportCell = number | string | null | ReportMoney[];

export type ReportTable = {
  key: string;
  label: string;
  definition: string;
  columns: string[];
  rows: { label: string; values: ReportCell[]; href: string | null }[];
  note: string | null;
};

export type FunnelStep = { key: string; label: string; count: number; definition: string };

export type Dashboard = {
  period: ReportPeriod;
  start: string;
  end: string;
  figures: ReportFigure[];
  tables: ReportTable[];
  funnel: FunnelStep[] | null;
};

export type SavedView = { id: string; name: string; path: string; query: string; shared: boolean; can_delete: boolean };

// --- email (slice 3.4) ---

export type DnsCheck = { status: "pass" | "fail" | "unknown"; record: string | null; advice: string | null };

export type Mailbox = {
  address: string;
  display_name: string;
  provider: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: "ssl" | "starttls";
  imap_host: string;
  imap_port: number;
  username: string;
  has_password: boolean;
  status: "unverified" | "connected" | "failing" | "disconnected";
  last_error: string | null;
  verified_at: string | null;
  dkim_selector: string | null;
  dns_checks: Partial<Record<"mx" | "spf" | "dkim" | "dmarc", DnsCheck>>;
  dns_checked_at: string | null;
  dns_ok: boolean;
  sending_enabled: boolean;
  daily_cap: number;
  last_synced_at: string | null;
  sending_allowed_by_admin: boolean;
};

export type MailboxState = { mailbox: Mailbox | null; sending_allowed_by_admin: boolean };

export type EmailPreflight = {
  ok: boolean;
  checks: { key: string; ok: boolean; message: string }[];
  recipient: string | null;
  sender: string | null;
  footer: string;
};

export type Email = {
  id: string;
  account_id: string;
  contact_id: string | null;
  contact_name: string | null;
  opportunity_id: string | null;
  deal_id: string | null;
  direction: "outbound" | "inbound";
  status: "sent" | "failed" | "received" | "bounced";
  from_address: string;
  to_address: string;
  subject: string;
  body_text: string;
  occurred_at: string;
  thread_key: string;
  classification: string | null;
  error: string | null;
};

// --- outreach (slice 3.5) ---

export type OutreachChannel = "email" | "linkedin" | "call";

export type OutreachTemplate = {
  id: string;
  name: string;
  channel: OutreachChannel;
  subject: string | null;
  body: string;
  service_id: string | null;
  industry: string | null;
  signal: string | null;
  is_active: boolean;
};

export type SequenceStep = { id: string; position: number; channel: OutreachChannel; delay_days: number; template_id: string | null; instructions: string | null };

export type OutreachSequence = { id: string; name: string; description: string | null; is_active: boolean; steps: SequenceStep[] };

export type OutreachDraft = { channel: OutreachChannel; subject: string | null; body: string; missing: string[]; reply_to_id: string | null };

export type SequencePreview = { sequence: string; steps: { position: number; channel: OutreachChannel; delay_days: number; due_at: string; draft: OutreachDraft }[] };

export type Enrollment = {
  id: string;
  sequence_id: string;
  sequence_name: string;
  contact_id: string;
  account_id: string;
  owner_id: string;
  status: "active" | "completed" | "stopped";
  stop_reason: string | null;
  next_position: number;
  total_steps: number;
  next_due_at: string | null;
  approved_at: string | null;
  created_at: string;
  history: { position: number; channel: OutreachChannel; outcome: string; note: string | null; done_at: string }[];
};

export type OutreachQueueItem = {
  enrollment_id: string;
  sequence_name: string;
  position: number;
  total_steps: number;
  channel: OutreachChannel;
  due_at: string | null;
  contact_id: string;
  contact_name: string;
  contact_title: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  account_id: string;
  account_name: string;
  priority_band: string | null;
  draft: OutreachDraft;
  linkedin_url: string | null;
  linkedin_is_search: boolean;
};

export type OutreachQueue = {
  items: OutreachQueueItem[];
  linkedin: { today: number; this_week: number; daily_limit: number; weekly_limit: number; blocked: string | null };
};
