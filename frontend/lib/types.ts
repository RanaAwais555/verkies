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

export type Run = {
  id: string;
  input_url: string;
  normalised_domain: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "retrying";
  review_status: "pending" | "approved" | "rejected";
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

export type BriefClaim = {
  claim_id: string;
  claim_class: "fact" | "inference" | "recommendation";
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
  match: "domain" | "name" | "flagged";
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

export type Contact = {
  id: string;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  decision_maker_role: string | null;
  verification_status: string;
  source: string;
  source_url: string | null;
  collected_at: string;
  confidence: number;
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
  status:
    | "pending"
    | "new"
    | "invalid"
    | "duplicate_in_file"
    | "existing_account"
    | "possible_duplicate"
    | "already_researched"
    | "suppressed"
    | "queued";
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
  status: "uploaded" | "checked";
  columns: string[];
  mapping: Record<string, string>;
  row_count: number;
  stats: Record<string, number>;
  created_by_id: string;
  created_at: string;
};

export type ImportDetail = ImportJob & { fields: string[]; rows: ImportRow[] };
