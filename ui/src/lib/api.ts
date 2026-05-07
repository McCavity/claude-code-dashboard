/**
 * Typed fetch wrappers for the FastAPI backend.
 *
 * Every endpoint surfaces here so panels do not call ``fetch`` directly.
 * Types mirror the JSON shapes the backend returns; if you add or rename
 * a field server-side, update both ends.
 */

const BASE = ""; // same-origin; vite dev server proxies /api and /v1.

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "omit" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return (await res.json()) as T;
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "omit",
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} on ${path}${txt ? ": " + txt : ""}`);
  }
  return (await res.json()) as T;
}

async function patchJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "omit",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return (await res.json()) as T;
}

async function deleteJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE", credentials: "omit" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return (await res.json()) as T;
}

// =============================================================================
// Types
// =============================================================================

export interface Health {
  ok: boolean;
  uptime_seconds: number;
  memory_mb: number | null;
  last_otel_event_age_s: number | null;
  last_sync_tick_age_s: number | null;
  last_notifier_tick_age_s: number | null;
  last_daemon_tick_age_s: number | null;
  otel_events_seen: number;
  otel_events_dropped: number;
  tz: string;
}

export interface Summary {
  sessions: number;
  tokens: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_create_tokens: number;
  tool_calls: number;
  errors: number;
}

export interface SessionListItem {
  session_id: string;
  source: string;
  cwd: string | null;
  cwd_short: string;
  git_branch: string | null;
  model: string | null;
  title: string | null;
  started_at: string;
  ended_at: string | null;
  total_tokens: number;
  effective_tokens: number;
  cost_usd: number | null;
  duration_ms: number | null;
  error_count: number;
  rate_limit_hit: number;
  stop_reason: string | null;
}

export interface SessionList {
  items: SessionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ToolCallRow {
  tool_use_id: string;
  tool_name: string;
  ts: string;
  duration_ms: number | null;
  error: string | null;
}

export interface SessionDetail {
  session: SessionListItem & {
    [k: string]: unknown;
  };
  tool_calls: ToolCallRow[];
  token_breakdown: Array<{
    date: string;
    model: string;
    source: string;
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens: number;
    cache_create_tokens: number;
  }>;
}

export interface OutcomeBucket {
  date: string;
  errored: number;
  rate_limited: number;
  truncated: number;
  unfinished: number;
  ok: number;
}

export interface SessionOutcomes {
  range: string;
  daily: OutcomeBucket[];
  totals: Omit<OutcomeBucket, "date">;
}

export interface ProjectRow {
  cwd: string;
  cwd_short: string;
  sessions: number;
  effective_tokens: number;
  total_tokens: number;
  tool_calls: number;
  share_pct: number;
}

export interface UsageTokensDay {
  date: string;
  input: number;
  output: number;
  cache_read: number;
  cache_create: number;
  total: number;
}

export interface UsageTokens {
  range: string;
  start: string;
  end: string;
  daily: UsageTokensDay[];
  by_model: Array<{ model: string; input: number; output: number; cache_read: number; cache_create: number }>;
  totals: { input: number; output: number; cache_read: number; cache_create: number };
}

export interface UsageCacheDay {
  date: string;
  input_tokens: number;
  cache_read_tokens: number;
  cache_create_tokens: number;
  billable: number;
  hit_rate: number;
}

export interface UsageCache {
  range: string;
  daily: UsageCacheDay[];
  overall_hit_rate: number;
  billable_tokens: number;
  low_sample: boolean;
  target: number;
}

export interface ToolLatencyRow {
  tool_name: string;
  calls: number;
  errors: number;
  error_rate: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
}

export interface ToolsLatency {
  range: string;
  items: ToolLatencyRow[];
}

export interface AgentFanoutRow {
  session_id: string;
  title: string | null;
  model: string | null;
  cwd_short: string;
  agent_calls: number;
}

export interface ToolsAgentFanout {
  range: string;
  items: AgentFanoutRow[];
}

export interface EditDecisionRow {
  tool_name: string;
  accept: number;
  reject: number;
  other: number;
  total: number;
  accept_rate: number;
}

export interface ToolsEditDecisions {
  range: string;
  items: EditDecisionRow[];
  low_sample: boolean;
  n: number;
}

export interface HooksActivity {
  range: string;
  total_fires: number;
  paired_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  daily: Array<{ date: string; fires: number }>;
}

export interface ActivityProductivity {
  range: string;
  daily: Array<{ date: string; commits: number; prs: number; lines: number }>;
  totals: Partial<{ commits: number; prs: number; lines: number }>;
}

export interface ContextHealth {
  settings_json: { path: string; exists: boolean; size_bytes?: number; lines?: number; modified_at?: string };
  claude_md: { path: string; exists: boolean; size_bytes?: number; lines?: number; modified_at?: string };
  mcp_servers: number;
  hooks_registered: number;
  permissions_allowed: number;
  plugins_enabled: string[];
}

export interface SkillEconomicsRow {
  skill_name: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_create_tokens: number;
  cost_usd: number;
  effective_tokens: number;
  total_tokens: number;
}

export interface SkillEconomics {
  range: string;
  items: SkillEconomicsRow[];
}

export interface FailureRow {
  session_id: string;
  title: string | null;
  model: string | null;
  cwd: string | null;
  cwd_short: string;
  error_count: number;
  rate_limit_hit: number;
  stop_reason: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface Failures {
  range: string;
  items: FailureRow[];
}

export interface SystemPressure {
  range: string;
  max_retries_threshold: number;
  retry_exhausted: number;
  compactions: number;
  recent_api_errors: Array<{
    timestamp: string;
    model: string | null;
    error_message: string | null;
    status_code: number | null;
    attempt_count: number | null;
  }>;
}

export interface McpServerRow {
  server: string;
  calls: number;
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  tools: number | null;
  total_tokens: number | null;
  measured_at: string | null;
}

export interface McpOverview {
  range: string;
  items: McpServerRow[];
}

export interface McpToolRow {
  tool: string;
  calls: number;
  errors: number;
  error_rate: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
}

export interface McpServerTools {
  server: string;
  range: string;
  items: McpToolRow[];
}

export interface SkillRow {
  name: string;
  environment: string;
  description: string | null;
  path: string | null;
  autonomy_level: "auto" | "review" | "manual";
  user_invocable: number;
  script_count: number;
  last_modified: string | null;
}

export interface SkillsList {
  items: SkillRow[];
}

export interface AttentionItem {
  kind: string;
  label: string;
  detail?: string;
  task_id?: number;
  severity: "warn" | "error" | "info";
}

export interface Attention {
  items: AttentionItem[];
  count: number;
}

export interface SystemStateRow {
  key: string;
  value: string | null;
  updated_at: string;
}

export interface SystemState {
  items: SystemStateRow[];
}

export interface LiveSessionRow {
  session_id: string;
  title: string | null;
  cwd: string | null;
  git_branch: string | null;
  model: string | null;
  started_at: string;
  total_tokens: number;
  last_tool_ts: string | null;
  tool_count: number;
  live_state: string | null;
  live_current_tool: string | null;
  live_updated_at: string | null;
  execution_mode: string | null;
}

export interface LiveSessions {
  items: LiveSessionRow[];
}

export interface LiveSessionState {
  session_id: string;
  state: string | null;
  current_tool: string | null;
  updated_at: string | null;
}

export interface Decision {
  id: number;
  task_id: number | null;
  session_id: string | null;
  prompt: string;
  answer: string | null;
  status: "pending" | "answered";
  created_at: string;
  answered_at: string | null;
}

export interface DecisionsList {
  items: Decision[];
}

export interface InboxMessage {
  id: number;
  task_id: number | null;
  session_id: string | null;
  direction: "agent_to_user" | "user_to_agent";
  body: string;
  read: number;
  created_at: string;
}

export interface InboxList {
  items: InboxMessage[];
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: "pending" | "awaiting_approval" | "running" | "done" | "failed" | "cancelled";
  priority: number;
  assigned_skill: string | null;
  model: string | null;
  execution_mode: "classic" | "stream";
  scheduled_for: string | null;
  requires_approval: number;
  risk_level: "low" | "medium" | "high";
  dry_run: number;
  quadrant: "do" | "schedule" | "delegate" | "archive";
  approved_at: string | null;
  session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  cost_usd: number | null;
  output_summary: string | null;
  error_message: string | null;
  consecutive_failures: number;
  created_at: string;
}

export interface TaskList {
  items: Task[];
}

export interface TaskCreateInput {
  title: string;
  description?: string;
  priority?: number;
  assigned_skill?: string;
  model?: string;
  execution_mode?: "classic" | "stream";
  scheduled_for?: string;
  requires_approval?: boolean;
  risk_level?: "low" | "medium" | "high";
  dry_run?: boolean;
  quadrant?: "do" | "schedule" | "delegate" | "archive";
}

export type TaskUpdateInput = Partial<TaskCreateInput & { status: Task["status"] }>;

export interface Schedule {
  id: number;
  name: string;
  cron_expression: string;
  task_title: string;
  task_description: string | null;
  assigned_skill: string | null;
  enabled: number;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
}

export interface ScheduleList {
  items: Schedule[];
  tz: string;
}

export interface ScheduleCreateInput {
  name: string;
  cron_expression: string;
  task_title: string;
  task_description?: string;
  assigned_skill?: string;
  enabled?: boolean;
}

export type ScheduleUpdateInput = Partial<ScheduleCreateInput>;

export interface ScheduleRuns {
  items: Array<{
    id: number;
    status: Task["status"];
    started_at: string | null;
    completed_at: string | null;
    duration_ms: number | null;
    output_summary: string | null;
    error_message: string | null;
    created_at: string;
  }>;
}

// =============================================================================
// Endpoints
// =============================================================================

export const api = {
  health: () => getJSON<Health>("/api/health"),
  systemHealth: () => getJSON<Health>("/api/system/health"),
  summary: () => getJSON<Summary>("/api/summary"),
  attention: () => getJSON<Attention>("/api/attention"),
  systemState: () => getJSON<SystemState>("/api/system/state"),
  emergencyStop: () =>
    postJSON<{ stopped: boolean; processes_killed: number; interactive_spared: number }>(
      "/api/system/emergency-stop"
    ),
  emergencyResume: () => postJSON<{ resumed: boolean }>("/api/system/emergency-resume"),

  sessions: (params: { range?: string; source?: string; model?: string; q?: string; limit?: number; offset?: number } = {}) =>
    getJSON<SessionList>(qs("/api/sessions", params)),
  sessionDetail: (id: string) => getJSON<SessionDetail>(`/api/sessions/${id}/details`),
  sessionsLive: () => getJSON<LiveSessions>("/api/sessions/live"),
  sessionLiveState: (id: string) => getJSON<LiveSessionState>(`/api/sessions/live/${id}/state`),
  sendLiveMessage: (id: string, body: string) =>
    postJSON<{ queued: boolean; queue_file: string }>(`/api/sessions/live/${id}/message`, { body }),
  sessionOutcomes: (range = "7d") => getJSON<SessionOutcomes>(`/api/sessions/outcomes?range=${range}`),
  sessionsByProject: (range = "30d") => getJSON<{ items: ProjectRow[] }>(`/api/sessions/by-project?range=${range}`),

  usageTokens: (range = "7d") => getJSON<UsageTokens>(`/api/usage/tokens?range=${range}`),
  usageCache: (range = "7d") => getJSON<UsageCache>(`/api/usage/cache?range=${range}`),

  toolsLatency: (range = "7d") => getJSON<ToolsLatency>(`/api/tools/latency?range=${range}`),
  toolsAgentFanout: (range = "7d") => getJSON<ToolsAgentFanout>(`/api/tools/agent-fanout?range=${range}`),
  toolsEditDecisions: (range = "7d") => getJSON<ToolsEditDecisions>(`/api/tools/edit-decisions?range=${range}`),

  hooksActivity: (range = "7d") => getJSON<HooksActivity>(`/api/hooks/activity?range=${range}`),
  productivity: (range = "30d") => getJSON<ActivityProductivity>(`/api/activity/productivity?range=${range}`),
  pressure: (range = "7d") => getJSON<SystemPressure>(`/api/system/pressure?range=${range}`),
  contextHealth: () => getJSON<ContextHealth>("/api/context-health"),
  skillEconomics: (range = "30d") => getJSON<SkillEconomics>(`/api/skills/economics?range=${range}`),
  failures: (range = "7d", limit = 30) => getJSON<Failures>(`/api/failures?range=${range}&limit=${limit}`),

  mcpOverview: (range = "30d") => getJSON<McpOverview>(`/api/mcp?range=${range}`),
  mcpTools: (server: string, range = "7d") =>
    getJSON<McpServerTools>(`/api/mcp/${encodeURIComponent(server)}/tools?range=${range}`),
  mcpSync: () => postJSON<{ synced: boolean; servers?: number; reason?: string }>("/api/mcp/sync"),
  mcpMeasure: () => postJSON<{ measured: boolean; servers?: number; reason?: string }>("/api/mcp/measure"),

  skills: (params: { environment?: string; user_invocable?: boolean } = {}) =>
    getJSON<SkillsList>(qs("/api/skills", params)),
  skillsSync: () => postJSON<{ synced: boolean; skills?: number; reason?: string }>("/api/skills/sync"),
  setSkillAutonomy: (name: string, body: { autonomy_level: "auto" | "review" | "manual"; environment?: string }) =>
    patchJSON<{ updated: number }>(`/api/skills/${encodeURIComponent(name)}/autonomy`, body),

  decisions: (status: "pending" | "answered" | "all" = "pending") =>
    getJSON<DecisionsList>(`/api/decisions?status=${status}`),
  answerDecision: (id: number, answer: string) =>
    postJSON<{ answered: boolean }>(`/api/decisions/${id}/answer`, { answer }),

  inbox: (params: { unread?: number; max_age_days?: number } = {}) =>
    getJSON<InboxList>(qs("/api/inbox", params)),
  markInboxRead: (id: number) => postJSON<{ read: boolean }>(`/api/inbox/${id}/read`),
  replyInbox: (id: number, body: string) =>
    postJSON<{ replied: boolean }>(`/api/inbox/${id}/reply`, { body }),

  tasks: (params: { status?: string; quadrant?: string; limit?: number } = {}) =>
    getJSON<TaskList>(qs("/api/tasks", params)),
  createTask: (body: TaskCreateInput) => postJSON<{ id: number; status: string }>("/api/tasks", body),
  updateTask: (id: number, body: TaskUpdateInput) =>
    patchJSON<{ updated: boolean }>(`/api/tasks/${id}`, body),
  deleteTask: (id: number) => deleteJSON<{ deleted: boolean }>(`/api/tasks/${id}`),
  approveTask: (id: number) => postJSON<{ approved: boolean }>(`/api/tasks/${id}/approve`),
  rerunTask: (id: number) => postJSON<{ rerun: boolean; task_id: number }>(`/api/tasks/${id}/rerun`),
  triggerDispatcher: () => postJSON<{ triggered: boolean; pid?: number; reason?: string }>("/api/dispatcher/trigger"),
  manualSync: () => postJSON<Record<string, unknown>>("/api/sync"),

  schedules: () => getJSON<ScheduleList>("/api/schedules"),
  createSchedule: (body: ScheduleCreateInput) =>
    postJSON<{ id: number; next_run_at: string | null }>("/api/schedules", body),
  updateSchedule: (id: number, body: ScheduleUpdateInput) =>
    patchJSON<{ updated: boolean }>(`/api/schedules/${id}`, body),
  deleteSchedule: (id: number) => deleteJSON<{ deleted: number; rowcount: number }>(`/api/schedules/${id}`),
  scheduleRuns: (id: number, limit = 10) =>
    getJSON<ScheduleRuns>(`/api/schedules/${id}/runs?limit=${limit}`),
  parseScheduleNL: (text: string) =>
    postJSON<{ cron: string; next_run_at: string }>("/api/schedules/parse-nl", { text }),
};

function qs(path: string, params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, typeof v === "boolean" ? (v ? "1" : "0") : String(v));
  }
  const q = sp.toString();
  return q ? `${path}?${q}` : path;
}
