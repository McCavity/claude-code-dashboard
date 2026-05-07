/**
 * Observability cards — eight panels rendered inside the
 * "Observability" CollapsibleSection of the Command page.
 *
 * Each panel has the same shape:
 *   1. Range picker (today / 7d / 30d) where applicable
 *   2. A condensed but information-dense data view
 *   3. A clear empty state when the API returns no data
 */

import { ReactNode, useState } from "react";
import { ArrowDown, ArrowUp, GitCommit, GitPullRequest, Hash } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardDescription, CardHeader, CardKicker, CardSkeleton, CardTitle } from "@/components/ui/Card";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  useAgentFanout,
  useEditDecisions,
  useHooksActivity,
  usePressure,
  useProductivity,
  useSessionOutcomes,
  useSessionsByProject,
  useToolsLatency,
} from "@/hooks/useQueries";
import { compact, dur, rel, thou } from "@/lib/format";

type Range = "today" | "7d" | "30d";

function RangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  const labels: Record<Range, string> = { today: "1d", "7d": "7d", "30d": "30d" };
  return (
    <div className="inline-flex rounded-md border border-border overflow-hidden bg-surface-2/40 text-xs">
      {(Object.keys(labels) as Range[]).map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => onChange(r)}
          className={r === value ? "px-2 py-1 text-text bg-surface" : "px-2 py-1 text-text-dim hover:text-text"}
        >
          {labels[r]}
        </button>
      ))}
    </div>
  );
}

function PanelShell({
  kicker,
  title,
  desc,
  range,
  setRange,
  children,
}: {
  kicker: string;
  title: string;
  desc?: string;
  range?: Range;
  setRange?: (r: Range) => void;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <CardKicker>{kicker}</CardKicker>
            <CardTitle>{title}</CardTitle>
            {desc ? <CardDescription>{desc}</CardDescription> : null}
          </div>
          {setRange && range ? <RangePicker value={range} onChange={setRange} /> : null}
        </div>
      </CardHeader>
      {children}
    </Card>
  );
}

// =============================================================================
// SessionOutcomesCard
// =============================================================================

const OUTCOME_KEYS = ["errored", "rate_limited", "truncated", "unfinished", "ok"] as const;
const OUTCOME_COLORS: Record<typeof OUTCOME_KEYS[number], string> = {
  errored: "bg-bad/80",
  rate_limited: "bg-warn/80",
  truncated: "bg-warn/50",
  unfinished: "bg-text-subtle/60",
  ok: "bg-good/70",
};
const OUTCOME_LABELS: Record<typeof OUTCOME_KEYS[number], string> = {
  errored: "errored",
  rate_limited: "rate-limited",
  truncated: "truncated",
  unfinished: "unfinished",
  ok: "ok",
};

export function SessionOutcomesCard() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = useSessionOutcomes(range);
  const max = data ? Math.max(...data.daily.map((d) => OUTCOME_KEYS.reduce((a, k) => a + d[k], 0)), 1) : 1;
  return (
    <PanelShell
      kicker="Session outcomes"
      title="Mutually exclusive buckets per day"
      desc="Priority order: errored → rate_limited → truncated → unfinished → ok"
      range={range}
      setRange={setRange}
    >
      {isLoading || !data ? (
        <CardSkeleton lines={4} />
      ) : data.daily.length === 0 ? (
        <p className="text-sm text-text-dim">No sessions in this window.</p>
      ) : (
        <>
          <div className="grid grid-cols-5 gap-2 text-[11px] mb-3">
            {OUTCOME_KEYS.map((k) => (
              <div key={k} className="flex items-center gap-1.5">
                <span className={`size-2.5 rounded-sm ${OUTCOME_COLORS[k]}`} />
                <span className="kicker text-[10px]">{OUTCOME_LABELS[k]}</span>
                <span className="ml-auto numeric font-mono text-text-dim">
                  {data.totals[k]}
                </span>
              </div>
            ))}
          </div>
          <div className="flex items-end gap-1 h-32 overflow-hidden">
            {data.daily.map((d) => (
              <div key={d.date} className="flex-1 flex flex-col-reverse gap-px" title={`${d.date}`}>
                {OUTCOME_KEYS.map((k) => {
                  const total = OUTCOME_KEYS.reduce((a, kk) => a + d[kk], 0);
                  return (
                    <div
                      key={k}
                      className={`${OUTCOME_COLORS[k]} rounded-sm`}
                      style={{
                        height: `${(d[k] / max) * 100}%`,
                        minHeight: d[k] > 0 ? 2 : 0,
                      }}
                      aria-label={`${OUTCOME_LABELS[k]} ${d[k]} of ${total} on ${d.date}`}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </>
      )}
    </PanelShell>
  );
}

// =============================================================================
// ToolLatencyCard
// =============================================================================

export function ToolLatencyCard() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = useToolsLatency(range);
  const top = data?.items.slice(0, 12) ?? [];
  return (
    <PanelShell
      kicker="Tool latency"
      title="p50 / p95 / max per tool"
      desc="Sorted by p95. Red ≥ 10s, green &lt; 500ms."
      range={range}
      setRange={setRange}
    >
      {isLoading ? (
        <CardSkeleton lines={6} />
      ) : top.length === 0 ? (
        <p className="text-sm text-text-dim">No tool calls in this window.</p>
      ) : (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase text-text-subtle">
              <tr className="text-left">
                <th className="px-2 py-1">tool</th>
                <th className="px-2 py-1 text-right">N</th>
                <th className="px-2 py-1 text-right">p50</th>
                <th className="px-2 py-1 text-right">p95</th>
                <th className="px-2 py-1 text-right">max</th>
                <th className="px-2 py-1 text-right">err</th>
              </tr>
            </thead>
            <tbody>
              {top.map((r) => (
                <tr key={r.tool_name} className="border-t border-border/40">
                  <td className="px-2 py-1 text-text font-mono truncate">{r.tool_name}</td>
                  <td className="px-2 py-1 text-right text-text-dim numeric font-mono">{thou(r.calls)}</td>
                  <td className="px-2 py-1 text-right text-text-dim numeric font-mono">{dur(r.p50_ms)}</td>
                  <td className={`px-2 py-1 text-right numeric font-mono ${
                    r.p95_ms !== null && r.p95_ms >= 10000 ? "text-bad" : r.p95_ms !== null && r.p95_ms < 500 ? "text-good" : "text-text"
                  }`}>{dur(r.p95_ms)}</td>
                  <td className="px-2 py-1 text-right text-text-dim numeric font-mono">{dur(r.max_ms)}</td>
                  <td className="px-2 py-1 text-right">
                    {r.error_rate > 0 ? (
                      <Badge tone={r.error_rate > 0.1 ? "bad" : "warn"} numeric>
                        {(r.error_rate * 100).toFixed(0)}%
                      </Badge>
                    ) : (
                      <span className="text-text-subtle">·</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PanelShell>
  );
}

// =============================================================================
// HookActivityCard
// =============================================================================

export function HookActivityCard() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = useHooksActivity(range);
  const max = data ? Math.max(...data.daily.map((d) => d.fires), 1) : 1;
  return (
    <PanelShell
      kicker="Hook activity"
      title={data ? `${thou(data.total_fires)} fires` : "Hook activity"}
      desc="Pre/Post-tool, Stop, SubagentStop. Durations capped at 60s."
      range={range}
      setRange={setRange}
    >
      {isLoading || !data ? (
        <CardSkeleton lines={3} />
      ) : data.total_fires === 0 ? (
        <p className="text-sm text-text-dim">
          No hook activity yet. Wire <code className="font-mono">session_state_hook.py</code> in <code className="font-mono">~/.claude/settings.json</code> to populate this.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 text-xs mb-3">
            <Stat label="paired" value={thou(data.paired_count)} />
            <Stat label="p50" value={dur(data.p50_ms)} />
            <Stat label="p95" value={dur(data.p95_ms)} />
          </div>
          <div className="flex items-end gap-px h-16">
            {data.daily.map((d) => (
              <div
                key={d.date}
                className="flex-1 bg-info/60 rounded-sm"
                style={{ height: `${(d.fires / max) * 100}%`, minHeight: d.fires > 0 ? 2 : 0 }}
                title={`${d.date}: ${d.fires}`}
              />
            ))}
          </div>
        </>
      )}
    </PanelShell>
  );
}

// =============================================================================
// ProjectBreakdownCard
// =============================================================================

export function ProjectBreakdownCard() {
  const [range, setRange] = useState<Range>("30d");
  const { data, isLoading } = useSessionsByProject(range);
  return (
    <PanelShell
      kicker="By project"
      title="Effective tokens per cwd"
      desc="Where the work actually went."
      range={range}
      setRange={setRange}
    >
      {isLoading ? (
        <CardSkeleton lines={5} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">No session activity in this window.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.slice(0, 10).map((p) => (
            <li key={p.cwd} className="grid grid-cols-[1fr_auto_auto_auto] gap-3 items-center text-xs">
              <span className="font-mono truncate text-text" title={p.cwd}>
                {p.cwd_short}
              </span>
              <span className="text-text-dim font-mono numeric">{thou(p.sessions)} sess</span>
              <span className="text-text font-mono numeric">{compact(p.effective_tokens)}</span>
              <Badge tone="neutral" numeric>{p.share_pct.toFixed(1)}%</Badge>
            </li>
          ))}
        </ul>
      )}
    </PanelShell>
  );
}

// =============================================================================
// AgentFanoutCard
// =============================================================================

export function AgentFanoutCard() {
  const [range, setRange] = useState<Range>("30d");
  const { data, isLoading } = useAgentFanout(range);
  return (
    <PanelShell
      kicker="Agent fan-out"
      title="Sessions that dispatched subagents"
      desc="Proxy for parallel work — each row is one parent session."
      range={range}
      setRange={setRange}
    >
      {isLoading ? (
        <CardSkeleton lines={4} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">No Agent calls in this window.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {data.items.slice(0, 8).map((s) => (
            <li key={s.session_id} className="flex items-center gap-3 text-xs">
              <span className="font-mono w-12 text-text numeric">{thou(s.agent_calls)}×</span>
              <span className="text-text truncate flex-1">
                {s.title ?? <span className="text-text-subtle font-mono">session: {s.session_id.slice(0, 8)}</span>}
              </span>
              <span className="text-text-dim font-mono">{s.cwd_short.split("/").pop()}</span>
            </li>
          ))}
        </ul>
      )}
    </PanelShell>
  );
}

// =============================================================================
// EditAcceptanceCard
// =============================================================================

export function EditAcceptanceCard() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = useEditDecisions(range);
  return (
    <PanelShell
      kicker="Edit acceptance"
      title="Accept rates for Edit / Write"
      desc="From OTEL tool_decision events. Requires OTEL_LOG_TOOL_DETAILS=1."
      range={range}
      setRange={setRange}
    >
      {isLoading ? (
        <CardSkeleton lines={4} />
      ) : data?.low_sample ? (
        <div className="text-sm text-text-dim flex items-center gap-2">
          <Badge tone="warn">low sample</Badge>
          {`fewer than 10 decisions in this window (n=${data.n})`}
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">No tool_decision events yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.map((row) => (
            <li key={row.tool_name} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 text-xs">
              <span className="font-mono w-24 text-text">{row.tool_name}</span>
              <div className="h-2 rounded bg-surface-2 overflow-hidden">
                <div
                  className="h-full bg-good"
                  style={{ width: `${(row.accept_rate * 100).toFixed(1)}%` }}
                />
              </div>
              <span className="numeric font-mono text-text-dim">
                {(row.accept_rate * 100).toFixed(0)}% · {row.total}
              </span>
            </li>
          ))}
        </ul>
      )}
    </PanelShell>
  );
}

// =============================================================================
// ProductivityCard
// =============================================================================

export function ProductivityCard() {
  const [range, setRange] = useState<Range>("30d");
  const { data, isLoading } = useProductivity(range);
  const isEmpty =
    data &&
    !data.totals.commits &&
    !data.totals.prs &&
    !data.totals.lines &&
    data.daily.length === 0;
  return (
    <PanelShell
      kicker="Productivity"
      title="Commits, PRs, lines"
      desc="OTEL metric counters claude_code.{commit,pull_request,lines_of_code}.count."
      range={range}
      setRange={setRange}
    >
      {isLoading ? (
        <CardSkeleton lines={3} />
      ) : isEmpty || !data ? (
        <p className="text-sm text-text-dim">
          No productivity counters yet — Claude Code emits these once a session
          commits / pushes a PR.
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          <BigStat
            icon={<GitCommit className="size-4" />}
            label="commits"
            value={thou(data.totals.commits ?? 0)}
            tone="accent"
          />
          <BigStat
            icon={<GitPullRequest className="size-4" />}
            label="PRs"
            value={thou(data.totals.prs ?? 0)}
            tone="info"
          />
          <BigStat
            icon={<Hash className="size-4" />}
            label="lines"
            value={compact(data.totals.lines ?? 0)}
            tone="good"
          />
        </div>
      )}
    </PanelShell>
  );
}

// =============================================================================
// PressurePanel
// =============================================================================

export function PressurePanel() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = usePressure(range);
  return (
    <PanelShell
      kicker="Pressure"
      title="Retries, compactions, recent API errors"
      desc={data ? `Threshold: attempt_count ≥ ${data.max_retries_threshold} (CLAUDE_CODE_MAX_RETRIES)` : ""}
      range={range}
      setRange={setRange}
    >
      {isLoading || !data ? (
        <CardSkeleton lines={3} />
      ) : (
        <div className="grid md:grid-cols-[1fr_auto_auto] gap-4 items-start">
          <div className="grid grid-cols-2 gap-3">
            <BigStat
              icon={<ArrowUp className="size-4" />}
              label="retry exhausted"
              value={thou(data.retry_exhausted)}
              tone={data.retry_exhausted > 0 ? "warn" : "neutral"}
            />
            <BigStat
              icon={<ArrowDown className="size-4" />}
              label="compactions"
              value={thou(data.compactions)}
              tone={data.compactions > 0 ? "info" : "neutral"}
            />
          </div>
          <div className="md:col-span-2">
            <CardKicker>Recent API errors</CardKicker>
            {data.recent_api_errors.length === 0 ? (
              <p className="text-sm text-text-dim mt-2">No API errors in this window. Nice.</p>
            ) : (
              <ul className="mt-2 flex flex-col gap-1 text-xs">
                {data.recent_api_errors.map((e, i) => (
                  <li key={i} className="grid grid-cols-[auto_auto_1fr_auto] gap-2 items-baseline">
                    <span className="text-text-subtle font-mono">{rel(e.timestamp)}</span>
                    <Tooltip content={`status ${e.status_code ?? "?"}, attempt ${e.attempt_count ?? "?"}`}>
                      <Badge tone={e.status_code === 429 ? "warn" : "bad"} numeric>
                        {e.status_code ?? "?"}
                      </Badge>
                    </Tooltip>
                    <span className="truncate text-text-dim">{e.error_message ?? "—"}</span>
                    <span className="text-text-subtle font-mono">{e.model ?? "—"}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </PanelShell>
  );
}

// =============================================================================
// shared bits
// =============================================================================

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="kicker text-[10px]">{label}</span>
      <span className="text-text font-mono numeric">{value}</span>
    </div>
  );
}

function BigStat({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
  icon: ReactNode;
  tone: "accent" | "info" | "good" | "warn" | "neutral";
}) {
  const cls = {
    accent: "text-accent-start",
    info: "text-info",
    good: "text-good",
    warn: "text-warn",
    neutral: "text-text-dim",
  }[tone];
  return (
    <div className="rounded-lg border border-border bg-surface-2/40 p-3 flex flex-col gap-1">
      <span className={`flex items-center gap-1 kicker text-[10px] ${cls}`}>
        {icon}
        {label}
      </span>
      <span className="text-2xl font-semibold tracking-tight numeric font-sans text-text">
        {value}
      </span>
    </div>
  );
}
