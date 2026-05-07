/**
 * Skills & MCP page — MCP drill-down centerpiece + skill economics +
 * read-only context health + skills registry with autonomy controls.
 */

import { ChevronRight, FileText, Settings, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardKicker, CardSkeleton, CardTitle } from "@/components/ui/Card";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import {
  useContextHealth,
  useMcpOverview,
  useMcpTools,
  useSkillEconomics,
  useSkills,
  useSystemMutations,
} from "@/hooks/useQueries";
import { compact, dur, rel, thou } from "@/lib/format";
import type { SkillRow } from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";

export function SkillsPage() {
  return (
    <div className="flex flex-col gap-6">
      <CollapsibleSection id="mcp" title="MCP servers" defaultOpen>
        <MCPPanel />
      </CollapsibleSection>

      <CollapsibleSection id="skill-econ" title="Skill economics" defaultOpen>
        <SkillCostCard />
      </CollapsibleSection>

      <CollapsibleSection id="ctx" title="Context health · registry" defaultOpen>
        <div className="grid gap-4 md:grid-cols-3">
          <ContextHealthCard />
          <div className="md:col-span-2">
            <SkillsRegistry />
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
}

// =============================================================================
// MCPPanel — the centerpiece
// =============================================================================

type Range = "7d" | "30d";

function MCPPanel() {
  const [range, setRange] = useState<Range>("30d");
  const { data, isLoading } = useMcpOverview(range);
  const { mcpSync } = useSystemMutations();
  const [open, setOpen] = useState<string | null>(null);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <CardKicker>MCP servers</CardKicker>
            <CardTitle>Sorted by p95 — slowest first</CardTitle>
            <CardDescription>
              Click a row to open the per-tool drill-down with p50/p95/max and error rate.
              Tools ≥ 10 s p95 get the slow tag; sub-500 ms gets the fast tag.
            </CardDescription>
          </div>
          <div className="inline-flex rounded-md border border-border overflow-hidden bg-surface-2/40 text-xs">
            {(["7d", "30d"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRange(r)}
                className={r === range ? "px-2 py-1 text-text bg-surface" : "px-2 py-1 text-text-dim hover:text-text"}
              >
                {r}
              </button>
            ))}
          </div>
          <Button size="sm" variant="secondary" loading={mcpSync.isPending} onClick={() => mcpSync.mutate()}>
            Sync
          </Button>
        </div>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={4} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">
          No MCP traffic yet. Use a tool whose name is <code className="font-mono">mcp__&lt;server&gt;__&lt;tool&gt;</code> and the dashboard will discover it.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {data.items.map((s) => {
            const expanded = open === s.server;
            return (
              <li key={s.server}>
                <button
                  type="button"
                  onClick={() => setOpen(expanded ? null : s.server)}
                  className="w-full grid grid-cols-[auto_1fr_auto_auto_auto_auto] items-center gap-3 py-3 text-left hover:bg-surface-2/40 px-2 -mx-2 rounded-md"
                >
                  <ChevronRight
                    className={`size-4 text-text-subtle transition-transform ${expanded ? "rotate-90" : ""}`}
                  />
                  <span className="font-mono text-text truncate">{s.server}</span>
                  <Badge tone="neutral" numeric>{thou(s.calls)} N</Badge>
                  <span className="text-xs text-text-dim font-mono numeric">avg {dur(s.avg_ms)}</span>
                  <span className="text-xs text-text font-mono numeric">p95 {dur(s.p95_ms)}</span>
                  <Badge
                    tone={s.p95_ms !== null && s.p95_ms >= 10_000 ? "bad" : s.p95_ms !== null && s.p95_ms < 500 ? "good" : "neutral"}
                  >
                    {s.p95_ms !== null && s.p95_ms >= 10_000 ? "slow" : s.p95_ms !== null && s.p95_ms < 500 ? "fast" : "—"}
                  </Badge>
                </button>
                <AnimatePresence initial={false}>
                  {expanded ? (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
                      className="overflow-hidden"
                    >
                      <McpToolBreakdown server={s.server} range={range} />
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function McpToolBreakdown({ server, range }: { server: string; range: Range }) {
  const { data, isLoading } = useMcpTools(server, range);
  if (isLoading) return <div className="py-3"><CardSkeleton lines={4} /></div>;
  if (!data || data.items.length === 0) {
    return <p className="text-xs text-text-dim py-3 px-2">No per-tool data for this window.</p>;
  }
  return (
    <div className="py-3 px-2">
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
          {data.items.map((t) => (
            <tr key={t.tool} className="border-t border-border/40">
              <td className="px-2 py-1 font-mono text-text">
                {t.tool}
                {t.p95_ms !== null && t.p95_ms >= 10_000 ? (
                  <span className="ml-2 text-bad">· slow</span>
                ) : t.p95_ms !== null && t.p95_ms < 500 ? (
                  <span className="ml-2 text-good">· fast</span>
                ) : null}
              </td>
              <td className="px-2 py-1 text-right font-mono numeric text-text-dim">{thou(t.calls)}</td>
              <td className="px-2 py-1 text-right font-mono numeric text-text-dim">{dur(t.p50_ms)}</td>
              <td className="px-2 py-1 text-right font-mono numeric text-text">{dur(t.p95_ms)}</td>
              <td className="px-2 py-1 text-right font-mono numeric text-text-dim">{dur(t.max_ms)}</td>
              <td className="px-2 py-1 text-right">
                {t.error_rate > 0 ? (
                  <Badge tone={t.error_rate > 0.1 ? "bad" : "warn"} numeric>
                    {(t.error_rate * 100).toFixed(0)}%
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
  );
}

// =============================================================================
// SkillCostCard
// =============================================================================

function SkillCostCard() {
  const { data, isLoading } = useSkillEconomics("30d");
  return (
    <Card>
      <CardHeader>
        <CardKicker>Skill economics</CardKicker>
        <CardTitle>Token + dollar cost per skill · 30 days</CardTitle>
        <CardDescription>
          Sourced from OTEL events with <code className="font-mono">skill.name</code> attribution.
          Cost is null when Claude Code didn't emit per-event cost.
        </CardDescription>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={5} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim">No skill-attributed events yet.</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase text-text-subtle">
            <tr className="text-left">
              <th className="px-2 py-1">skill</th>
              <th className="px-2 py-1 text-right">calls</th>
              <th className="px-2 py-1 text-right">tokens</th>
              <th className="px-2 py-1 text-right">effective</th>
              <th className="px-2 py-1 text-right">cost</th>
            </tr>
          </thead>
          <tbody>
            {data.items.slice(0, 20).map((r) => (
              <tr key={r.skill_name} className="border-t border-border/40">
                <td className="px-2 py-1 font-mono text-text truncate">{r.skill_name}</td>
                <td className="px-2 py-1 text-right text-text-dim font-mono numeric">{thou(r.calls)}</td>
                <td className="px-2 py-1 text-right text-text-dim font-mono numeric">{compact(r.total_tokens)}</td>
                <td className="px-2 py-1 text-right text-text font-mono numeric">{compact(r.effective_tokens)}</td>
                <td className="px-2 py-1 text-right text-text-dim font-mono numeric">
                  {r.cost_usd ? `$${r.cost_usd.toFixed(3)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// =============================================================================
// ContextHealthCard
// =============================================================================

function ContextHealthCard() {
  const { data, isLoading } = useContextHealth();
  return (
    <Card>
      <CardHeader>
        <CardKicker>Context health</CardKicker>
        <CardTitle>~/.claude scan</CardTitle>
        <CardDescription>Read-only. Not an LLM call.</CardDescription>
      </CardHeader>
      {isLoading || !data ? (
        <CardSkeleton lines={4} />
      ) : (
        <ul className="flex flex-col gap-3 text-xs">
          <FileLine icon={<Settings className="size-3.5" />} label="settings.json" file={data.settings_json} />
          <FileLine icon={<FileText className="size-3.5" />} label="CLAUDE.md" file={data.claude_md} />
          <li className="grid grid-cols-2 gap-3">
            <Stat label="MCP servers" value={String(data.mcp_servers)} />
            <Stat label="Hooks" value={String(data.hooks_registered)} />
            <Stat label="Permissions" value={String(data.permissions_allowed)} />
            <Stat label="Plugins" value={String(data.plugins_enabled.length)} />
          </li>
          {data.plugins_enabled.length ? (
            <li>
              <span className="kicker text-[10px]">Plugins enabled</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {data.plugins_enabled.map((p) => (
                  <Badge key={p} tone="accent" numeric>{p}</Badge>
                ))}
              </div>
            </li>
          ) : null}
        </ul>
      )}
    </Card>
  );
}

function FileLine({
  icon,
  label,
  file,
}: {
  icon: React.ReactNode;
  label: string;
  file: { path: string; exists: boolean; size_bytes?: number; lines?: number; modified_at?: string };
}) {
  return (
    <li className="flex items-baseline gap-2 font-mono text-[11px]">
      <span className="text-text-subtle">{icon}</span>
      <span className="text-text">{label}</span>
      {file.exists ? (
        <>
          <span className="text-text-dim">· {file.lines ?? 0} lines</span>
          <span className="text-text-dim">· {file.size_bytes ?? 0} B</span>
          <span className="ml-auto text-text-subtle">{rel(file.modified_at ?? null)}</span>
        </>
      ) : (
        <Badge tone="warn">missing</Badge>
      )}
    </li>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border bg-surface-2/40 p-2 flex flex-col gap-0.5">
      <span className="kicker text-[10px]">{label}</span>
      <span className="text-text font-mono numeric text-lg">{value}</span>
    </div>
  );
}

// =============================================================================
// SkillsRegistry
// =============================================================================

const ENV_LABEL: Record<string, string> = {
  "ide:project": "IDE · project",
  "ide:global": "IDE · global",
  "cowork:plugin": "Cowork · plugin",
  "cowork:scheduled": "Cowork · scheduled",
};

function SkillsRegistry() {
  const { data, isLoading } = useSkills();
  const { setSkillAutonomy, skillsSync } = useSystemMutations();

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <CardKicker>Skills registry</CardKicker>
            <CardTitle>{data ? `${data.items.length} skills` : "Skills"}</CardTitle>
            <CardDescription>
              Set autonomy per skill: <em>auto</em> runs without intervention,
              <em> review</em> stops in awaiting_approval, <em>manual</em> never auto-runs.
            </CardDescription>
          </div>
          <Button size="sm" variant="secondary" loading={skillsSync.isPending} onClick={() => skillsSync.mutate()}>
            Resync
          </Button>
        </div>
      </CardHeader>
      {isLoading ? (
        <CardSkeleton lines={6} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-text-dim flex items-center gap-2">
          <ShieldCheck className="size-4 text-text-subtle" />
          No skills indexed yet. Run <code className="font-mono">cc sync</code> or queue a task that uses one.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {data.items.map((s) => (
            <SkillRowItem
              key={`${s.environment}:${s.name}`}
              skill={s}
              onSetAutonomy={(level) =>
                setSkillAutonomy.mutate({
                  name: s.name,
                  body: { autonomy_level: level, environment: s.environment },
                })
              }
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function SkillRowItem({
  skill,
  onSetAutonomy,
}: {
  skill: SkillRow;
  onSetAutonomy: (level: "auto" | "review" | "manual") => void;
}) {
  return (
    <li className="py-3 grid grid-cols-[1fr_auto_auto] items-center gap-3">
      <div className="min-w-0">
        <div className="text-sm text-text font-mono">{skill.name}</div>
        <div className="text-[11px] text-text-subtle font-mono truncate">
          {ENV_LABEL[skill.environment] ?? skill.environment} · {skill.path ?? "—"}
        </div>
        {skill.description ? (
          <div className="text-xs text-text-dim line-clamp-1 mt-1">{skill.description}</div>
        ) : null}
      </div>
      {skill.user_invocable ? <Badge tone="info">user-invocable</Badge> : null}
      <div className="inline-flex rounded-md border border-border overflow-hidden bg-surface-2/40 text-xs">
        {(["auto", "review", "manual"] as const).map((level) => (
          <button
            key={level}
            type="button"
            onClick={() => onSetAutonomy(level)}
            className={
              skill.autonomy_level === level
                ? "px-2 py-1 text-text bg-surface"
                : "px-2 py-1 text-text-dim hover:text-text"
            }
          >
            {level}
          </button>
        ))}
      </div>
    </li>
  );
}
