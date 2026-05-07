/**
 * Top-of-page system panels:
 *  - SystemHealthStrip   uptime / memory / OTEL & sync ages
 *  - KpiRow              today's headline numbers
 *  - AttentionBar        red-banner aggregator
 *  - EmergencyStopBanner one-button "stop everything" with confirm
 */

import { AlertTriangle, OctagonAlert, ShieldOff, Square } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardKicker, CardSkeleton } from "@/components/ui/Card";
import { StatePill } from "@/components/ui/StatePill";
import { Tooltip } from "@/components/ui/Tooltip";
import { useAttention, useHealth, useSummary, useSystemMutations } from "@/hooks/useQueries";
import { compact, dur, thou } from "@/lib/format";

// =============================================================================
// SystemHealthStrip
// =============================================================================

export function SystemHealthStrip() {
  const { data, isLoading } = useHealth();
  if (isLoading || !data) {
    return (
      <Card>
        <CardSkeleton lines={1} />
      </Card>
    );
  }
  return (
    <Card className="flex items-center gap-6 flex-wrap py-3">
      <PillRow
        label="uptime"
        value={dur(data.uptime_seconds * 1000)}
        state="active"
      />
      <PillRow
        label="memory"
        value={data.memory_mb !== null ? `${data.memory_mb.toFixed(0)} MB` : "—"}
        state={data.memory_mb && data.memory_mb > 1024 ? "warning" : "active"}
      />
      <PillRow
        label="otel"
        value={
          data.last_otel_event_age_s === null
            ? "never"
            : dur(data.last_otel_event_age_s * 1000)
        }
        state={ageState(data.last_otel_event_age_s, 600, 3600)}
      />
      <PillRow
        label="sync"
        value={
          data.last_sync_tick_age_s === null
            ? "boot"
            : dur(data.last_sync_tick_age_s * 1000)
        }
        state={ageState(data.last_sync_tick_age_s, 180, 600)}
      />
      <PillRow
        label="daemon"
        value={
          data.last_daemon_tick_age_s === null
            ? "off"
            : dur(data.last_daemon_tick_age_s * 1000)
        }
        state={ageState(data.last_daemon_tick_age_s, 180, 900)}
      />
      <PillRow
        label="notifier"
        value={
          data.last_notifier_tick_age_s === null
            ? "off"
            : dur(data.last_notifier_tick_age_s * 1000)
        }
        state={data.last_notifier_tick_age_s === null ? "idle" : "active"}
      />
      <span className="ml-auto text-xs text-text-subtle font-mono">
        events {compact(data.otel_events_seen)} · dropped {compact(data.otel_events_dropped)} · {data.tz}
      </span>
    </Card>
  );
}

function ageState(age: number | null, warnAt: number, errorAt: number) {
  if (age === null) return "idle";
  if (age >= errorAt) return "error";
  if (age >= warnAt) return "warning";
  return "active";
}

function PillRow({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state: "idle" | "active" | "warning" | "error" | "unknown";
}) {
  return (
    <div className="flex items-baseline gap-2">
      <StatePill state={state} pulsing={state === "active"} />
      <span className="kicker">{label}</span>
      <span className="font-mono numeric text-sm text-text">{value}</span>
    </div>
  );
}

// =============================================================================
// KpiRow
// =============================================================================

export function KpiRow() {
  const { data, isLoading } = useSummary();
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {KPIS.map((k) => (
        <KpiTile
          key={k.id}
          label={k.label}
          value={isLoading || !data ? null : k.read(data)}
          accent={k.accent}
          hint={k.hint}
        />
      ))}
    </div>
  );
}

const KPIS = [
  {
    id: "sessions",
    label: "Sessions today",
    read: (d: { sessions: number }) => thou(d.sessions),
    accent: "accent" as const,
    hint: "JSONL sessions started today, local time.",
  },
  {
    id: "tokens",
    label: "Tokens today",
    read: (d: { tokens: number }) => compact(d.tokens),
    accent: "info" as const,
    hint: "Sum of input + output + cache reads + cache creates today.",
  },
  {
    id: "tools",
    label: "Tool calls",
    read: (d: { tool_calls: number }) => thou(d.tool_calls),
    accent: "neutral" as const,
    hint: "Top-level tool invocations (no subagent fan-out).",
  },
  {
    id: "errors",
    label: "Errors",
    read: (d: { errors: number }) => thou(d.errors),
    accent: "bad" as const,
    hint: "Sessions with at least one tool_result is_error=true OR system level=error.",
  },
];

function KpiTile({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: string | null;
  accent: "accent" | "info" | "neutral" | "bad";
  hint: string;
}) {
  return (
    <Card className="py-5">
      <Tooltip content={hint} side="bottom">
        <span className="kicker">{label}</span>
      </Tooltip>
      <div className="mt-2 flex items-baseline gap-3">
        {value === null ? (
          <span className="skeleton h-8 w-24" />
        ) : (
          <span className="text-3xl font-semibold tracking-tight numeric font-sans">
            {value}
          </span>
        )}
        <Badge tone={accent} numeric>
          today
        </Badge>
      </div>
    </Card>
  );
}

// =============================================================================
// AttentionBar
// =============================================================================

export function AttentionBar() {
  const { data } = useAttention();
  if (!data || data.count === 0) return null;
  return (
    <Card
      className="border-bad/40 bg-bad/5"
      role="alert"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-bad">
          <AlertTriangle className="size-4" />
        </span>
        <div className="flex-1">
          <CardKicker className="text-bad">Attention</CardKicker>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {data.items.map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <SeverityDot severity={item.severity} />
                <span className="text-text">{item.label}</span>
                {item.detail ? (
                  <span className="text-text-dim line-clamp-1">— {item.detail}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function SeverityDot({ severity }: { severity: "warn" | "error" | "info" }) {
  const cls =
    severity === "error"
      ? "bg-bad"
      : severity === "warn"
        ? "bg-warn"
        : "bg-info";
  return <span className={`mt-1.5 size-2 rounded-full ${cls}`} aria-hidden />;
}

// =============================================================================
// EmergencyStopBanner
// =============================================================================

export function EmergencyStopBanner() {
  const [confirming, setConfirming] = useState(false);
  const { emergencyStop, emergencyResume } = useSystemMutations();
  const stopped = emergencyStop.data?.stopped;

  return (
    <Card className="border-bad/30 bg-bad/5">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-bad">
          <ShieldOff className="size-5" />
        </span>
        <div className="flex-1">
          <CardKicker className="text-bad">Emergency stop</CardKicker>
          <p className="text-sm text-text-dim">
            Sends SIGTERM to every dispatched <code className="font-mono">claude -p</code> child.
            Interactive sessions in your own terminal are spared (PID file gating).
          </p>
        </div>
        {stopped ? (
          <Button
            variant="secondary"
            size="md"
            onClick={() => emergencyResume.mutate()}
            loading={emergencyResume.isPending}
          >
            Resume
          </Button>
        ) : confirming ? (
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="md" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="md"
              onClick={() => {
                emergencyStop.mutate(undefined, {
                  onSettled: () => setConfirming(false),
                });
              }}
              loading={emergencyStop.isPending}
            >
              <OctagonAlert className="size-4" /> Confirm stop
            </Button>
          </div>
        ) : (
          <Button variant="danger" size="md" onClick={() => setConfirming(true)}>
            <Square className="size-4" /> Stop dispatched runs
          </Button>
        )}
      </div>
      {emergencyStop.data ? (
        <p className="mt-2 text-xs text-text-dim">
          {emergencyStop.data.processes_killed} killed,{" "}
          {emergencyStop.data.interactive_spared} spared.
        </p>
      ) : null}
    </Card>
  );
}
