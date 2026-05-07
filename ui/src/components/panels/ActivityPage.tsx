/**
 * Activity page — patterns, firehose, top skills, failures, sessions
 * table.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Search, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardDescription, CardHeader, CardKicker, CardSkeleton, CardTitle } from "@/components/ui/Card";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { useFailures, useSessions, useSkillEconomics, useUsageTokens } from "@/hooks/useQueries";
import { compact, dur, rel, thou } from "@/lib/format";

export function ActivityPage() {
  return (
    <div className="flex flex-col gap-6">
      <CollapsibleSection id="patterns" title="Patterns" defaultOpen>
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <HeatmapGrid />
          <ChartsStrip />
        </div>
      </CollapsibleSection>

      <CollapsibleSection id="firehose" title="Telemetry firehose">
        <OtelPanel />
      </CollapsibleSection>

      <CollapsibleSection id="skills-failures" title="Top skills · failures" defaultOpen>
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <TopSkillsCard />
          <UnifiedFailuresCard />
        </div>
      </CollapsibleSection>

      <CollapsibleSection id="sessions-table" title="All sessions" defaultOpen>
        <SessionsTable />
      </CollapsibleSection>
    </div>
  );
}

// =============================================================================
// HeatmapGrid — 30 days × buckets-per-day token intensity
// =============================================================================

function HeatmapGrid() {
  const { data, isLoading } = useUsageTokens("30d");
  const { rows, max } = useMemo(() => {
    if (!data) return { rows: [], max: 0 };
    const map = new Map(data.daily.map((d) => [d.date, d.total]));
    const today = new Date();
    const list: Array<{ date: string; total: number }> = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const iso = d.toISOString().slice(0, 10);
      list.push({ date: iso, total: map.get(iso) ?? 0 });
    }
    return { rows: list, max: Math.max(1, ...list.map((r) => r.total)) };
  }, [data]);
  return (
    <Card>
      <CardHeader>
        <CardKicker>30-day intensity</CardKicker>
        <CardTitle>Where the work happened</CardTitle>
        <CardDescription>One cell per day, shade = total tokens.</CardDescription>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={3} />
      ) : (
        <div className="grid grid-cols-10 gap-1.5">
          {rows.map((r) => {
            const f = r.total / max;
            return (
              <div
                key={r.date}
                title={`${r.date}: ${compact(r.total)} tokens`}
                className="aspect-square rounded-sm border border-border"
                style={{
                  backgroundColor:
                    r.total === 0
                      ? "var(--surface)"
                      : `rgba(77,124,255,${0.2 + 0.7 * f})`,
                }}
              />
            );
          })}
        </div>
      )}
    </Card>
  );
}

// =============================================================================
// ChartsStrip — 14-day stacked tokens by model
// =============================================================================

function ChartsStrip() {
  const { data, isLoading } = useUsageTokens("30d");
  const last14 = data ? data.daily.slice(-14) : [];
  const max = Math.max(1, ...last14.map((d) => d.total));
  return (
    <Card>
      <CardHeader>
        <CardKicker>Last 14 days</CardKicker>
        <CardTitle>Daily total tokens</CardTitle>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={3} />
      ) : last14.length === 0 ? (
        <p className="text-sm text-text-dim">No data yet.</p>
      ) : (
        <>
          <div className="flex items-end gap-1 h-44">
            {last14.map((d) => (
              <div
                key={d.date}
                className="flex-1 flex flex-col-reverse gap-px"
                title={`${d.date}: ${compact(d.total)}`}
              >
                <div className="bg-info/70 rounded-sm" style={{ height: `${(d.input / max) * 100}%` }} />
                <div className="bg-accent-start/80 rounded-sm" style={{ height: `${(d.output / max) * 100}%` }} />
                <div className="bg-good/60 rounded-sm" style={{ height: `${(d.cache_read / max) * 100}%` }} />
                <div className="bg-warn/60 rounded-sm" style={{ height: `${(d.cache_create / max) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-text-subtle font-mono">
            <span>{last14[0]?.date.slice(5)}</span>
            <span>{last14.at(-1)?.date.slice(5)}</span>
          </div>
        </>
      )}
    </Card>
  );
}

// =============================================================================
// OtelPanel — SSE firehose
// =============================================================================

interface FirehoseEvent {
  id: number;
  event_name: string;
  session_id: string | null;
  model: string | null;
  tool_name: string | null;
  tool_duration_ms: number | null;
  mcp_server_name: string | null;
  mcp_tool_name: string | null;
  timestamp: string;
}

function OtelPanel() {
  const [events, setEvents] = useState<FirehoseEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    const es = new EventSource("/api/firehose");
    es.onopen = () => setStatus("open");
    es.onerror = () => setStatus("closed");
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as FirehoseEvent;
        setEvents((prev) => [ev, ...prev].slice(0, 200));
      } catch {
        /* ignore */
      }
    };
    return () => es.close();
  }, []);

  const filtered = filter
    ? events.filter((e) =>
        [e.event_name, e.tool_name, e.mcp_server_name, e.mcp_tool_name, e.model]
          .filter(Boolean)
          .some((s) => (s as string).toLowerCase().includes(filter.toLowerCase())),
      )
    : events;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <CardKicker>OTEL firehose</CardKicker>
            <CardTitle>
              Live · <Badge tone={status === "open" ? "good" : status === "closed" ? "bad" : "warn"}>{status}</Badge>
            </CardTitle>
            <CardDescription>
              SSE stream of every <code className="font-mono">/v1/logs</code> insert. Newest first; capped at 200.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 rounded-md border border-border bg-surface-2/40 px-2 h-9">
            <Search className="size-3.5 text-text-subtle" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="filter event_name, tool, model…"
              className="bg-transparent text-xs outline-none placeholder:text-text-subtle w-56"
            />
          </div>
        </div>
      </CardHeader>
      {filtered.length === 0 ? (
        <p className="text-sm text-text-dim flex items-center gap-2">
          <Sparkles className="size-4 text-text-subtle" />
          Waiting for telemetry — make sure OTEL is enabled and Claude Code is running.
        </p>
      ) : (
        <ul className="flex flex-col gap-1 max-h-[420px] overflow-y-auto pr-1">
          {filtered.map((e) => (
            <li
              key={e.id}
              className="grid grid-cols-[auto_auto_1fr_auto] gap-2 items-baseline text-xs font-mono numeric border-b border-border/30 py-1"
            >
              <span className="text-text-subtle">{e.timestamp.slice(11, 19)}</span>
              <Badge tone={tagToneFor(e.event_name)}>{e.event_name}</Badge>
              <span className="text-text truncate">
                {e.mcp_server_name ? `${e.mcp_server_name}.${e.mcp_tool_name ?? "?"}` : e.tool_name ?? "—"}
              </span>
              <span className="text-text-dim">{dur(e.tool_duration_ms)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function tagToneFor(name: string) {
  if (name === "tool_result") return "neutral" as const;
  if (name === "api_error") return "bad" as const;
  if (name === "api_request") return "info" as const;
  if (name === "compaction") return "warn" as const;
  if (name.startsWith("hook_")) return "accent" as const;
  return "neutral" as const;
}

// =============================================================================
// TopSkillsCard — token cost per skill (from OTEL skill.name)
// =============================================================================

function TopSkillsCard() {
  const { data, isLoading } = useSkillEconomics("30d");
  return (
    <Card>
      <CardHeader>
        <CardKicker>Top skills</CardKicker>
        <CardTitle>By effective tokens · 30 days</CardTitle>
        <CardDescription>
          Sum of output + cache_create on OTEL events that carried a skill name.
          Empty when OTEL is off or no skill attribution landed.
        </CardDescription>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={5} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">No skill-attributed events in this window.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.slice(0, 10).map((row) => (
            <li key={row.skill_name} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 text-xs">
              <span className="font-mono text-text truncate">{row.skill_name}</span>
              <span className="text-text font-mono numeric">{compact(row.effective_tokens)}</span>
              <Badge tone="neutral" numeric>{thou(row.calls)}×</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// =============================================================================
// UnifiedFailuresCard
// =============================================================================

function UnifiedFailuresCard() {
  const { data, isLoading } = useFailures("7d");
  return (
    <Card>
      <CardHeader>
        <CardKicker>Failures</CardKicker>
        <CardTitle>Sessions that hit errors · 7 days</CardTitle>
        <CardDescription>
          Includes <code className="font-mono">error_count &gt; 0</code>, rate-limit hits,
          and <code className="font-mono">stop_reason='error'</code>.
        </CardDescription>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={5} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim flex items-center gap-2">
          <AlertCircle className="size-4 text-good" />
          No failures in this window.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.slice(0, 10).map((s) => (
            <li key={s.session_id} className="grid grid-cols-[1fr_auto_auto] items-baseline gap-3 text-xs">
              <span className="text-text truncate">{s.title ?? <span className="text-text-subtle font-mono">{s.session_id.slice(0, 8)}</span>}</span>
              <Badge tone="bad" numeric>{thou(s.error_count)} err</Badge>
              <span className="text-text-subtle font-mono">{rel(s.started_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// =============================================================================
// SessionsTable — searchable, filterable, paginated
// =============================================================================

function SessionsTable() {
  const [q, setQ] = useState("");
  const [range, setRange] = useState<"today" | "7d" | "30d">("30d");
  const [offset, setOffset] = useState(0);
  const limit = 25;
  const { data, isLoading } = useSessions({ q, range, limit, offset });
  const ref = useRef<HTMLInputElement>(null);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <CardKicker>Sessions</CardKicker>
            <CardTitle>{data ? `${thou(data.total)} matches` : "Searching…"}</CardTitle>
            <CardDescription>Filter by title or cwd. Click a row to open the live drawer.</CardDescription>
          </div>
          <div className="flex items-center gap-2 rounded-md border border-border bg-surface-2/40 px-2 h-9">
            <Search className="size-3.5 text-text-subtle" />
            <input
              ref={ref}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
              placeholder="title or cwd"
              className="bg-transparent text-xs outline-none placeholder:text-text-subtle w-56"
            />
          </div>
          <div className="inline-flex rounded-md border border-border overflow-hidden bg-surface-2/40 text-xs">
            {(["today", "7d", "30d"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => {
                  setRange(r);
                  setOffset(0);
                }}
                className={r === range ? "px-2.5 py-1 text-text bg-surface" : "px-2.5 py-1 text-text-dim hover:text-text"}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={6} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">No sessions match.</p>
      ) : (
        <>
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase text-text-subtle">
                <tr className="text-left">
                  <th className="px-2 py-1">Title</th>
                  <th className="px-2 py-1">Project</th>
                  <th className="px-2 py-1">Model</th>
                  <th className="px-2 py-1 text-right">Tokens</th>
                  <th className="px-2 py-1 text-right">Errors</th>
                  <th className="px-2 py-1">Started</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((s) => (
                  <tr key={s.session_id} className="border-t border-border/40 hover:bg-surface-2/40">
                    <td className="px-2 py-1.5 text-text truncate max-w-[280px]">{s.title ?? <span className="font-mono text-text-subtle">{s.session_id.slice(0, 8)}</span>}</td>
                    <td className="px-2 py-1.5 text-text-dim font-mono truncate max-w-[260px]">{s.cwd_short}</td>
                    <td className="px-2 py-1.5 text-text-dim font-mono">{s.model ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right font-mono numeric text-text">{compact(s.total_tokens)}</td>
                    <td className="px-2 py-1.5 text-right">
                      {s.error_count ? <Badge tone="bad" numeric>{s.error_count}</Badge> : <span className="text-text-subtle">·</span>}
                    </td>
                    <td className="px-2 py-1.5 text-text-subtle">{rel(s.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2 text-xs">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
              className="px-2 py-1 rounded border border-border text-text-dim disabled:opacity-40"
            >
              ← prev
            </button>
            <span className="text-text-subtle font-mono">
              {offset + 1}–{offset + data.items.length}
            </span>
            <button
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(offset + limit)}
              className="px-2 py-1 rounded border border-border text-text-dim disabled:opacity-40"
            >
              next →
            </button>
          </div>
        </>
      )}
    </Card>
  );
}
