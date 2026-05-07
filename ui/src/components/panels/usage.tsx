/**
 * TokenUsageCard      stacked daily bars (input / output / cache_read / cache_create)
 * CacheEfficiencyCard hit-rate big number + 14-day trend sparkline + target line
 *
 * Both default to today/7d/30d toggles and refresh on the standard
 * 30 s poll cadence.
 */

import { useState } from "react";
import { Card, CardHeader, CardKicker, CardSkeleton, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useUsageCache, useUsageTokens } from "@/hooks/useQueries";
import { compact } from "@/lib/format";

type Range = "today" | "7d" | "30d";

const RANGE_LABEL: Record<Range, string> = {
  today: "Today",
  "7d": "7 days",
  "30d": "30 days",
};

function RangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <div className="inline-flex rounded-md border border-border overflow-hidden bg-surface-2/40 text-xs">
      {(Object.keys(RANGE_LABEL) as Range[]).map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => onChange(r)}
          className={
            r === value
              ? "px-2.5 py-1 text-text bg-surface"
              : "px-2.5 py-1 text-text-dim hover:text-text"
          }
        >
          {RANGE_LABEL[r]}
        </button>
      ))}
    </div>
  );
}

// =============================================================================
// TokenUsageCard
// =============================================================================

export function TokenUsageCard() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = useUsageTokens(range);

  const total = data
    ? data.totals.input + data.totals.output + data.totals.cache_read + data.totals.cache_create
    : 0;

  const max = data ? Math.max(...data.daily.map((d) => d.total), 1) : 1;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1">
            <CardKicker>Token usage</CardKicker>
            <CardTitle>{compact(total)} tokens · {RANGE_LABEL[range].toLowerCase()}</CardTitle>
            <CardDescription>
              Stacked input / output / cache-read / cache-create. Totals roll up by local-time day.
            </CardDescription>
          </div>
          <RangePicker value={range} onChange={setRange} />
        </div>
      </CardHeader>
      {isLoading || !data ? (
        <CardSkeleton lines={4} />
      ) : data.daily.length === 0 ? (
        <EmptyTokens />
      ) : (
        <>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <Legend label="input" tone="info" total={data.totals.input} />
            <Legend label="output" tone="accent" total={data.totals.output} />
            <Legend label="cache read" tone="good" total={data.totals.cache_read} />
            <Legend label="cache create" tone="warn" total={data.totals.cache_create} />
          </div>
          <div className="flex items-end gap-1 h-40 overflow-hidden">
            {data.daily.map((d) => (
              <div
                key={d.date}
                className="flex-1 flex flex-col-reverse gap-px"
                title={`${d.date}: ${compact(d.total)} total`}
              >
                <Segment frac={d.input / max} className="bg-info/70" />
                <Segment frac={d.output / max} className="bg-accent-start/80" />
                <Segment frac={d.cache_read / max} className="bg-good/60" />
                <Segment frac={d.cache_create / max} className="bg-warn/60" />
              </div>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-text-subtle font-mono numeric">
            <span>{data.daily[0]?.date.slice(5)}</span>
            <span>{data.daily.at(-1)?.date.slice(5)}</span>
          </div>
        </>
      )}
    </Card>
  );
}

function Segment({ frac, className }: { frac: number; className: string }) {
  return (
    <div
      className={`${className} rounded-sm transition-all duration-300`}
      style={{ height: `${Math.max(0, frac * 100)}%`, minHeight: frac > 0 ? 1 : 0 }}
    />
  );
}

function Legend({
  label,
  tone,
  total,
}: {
  label: string;
  tone: "info" | "accent" | "good" | "warn";
  total: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={
        tone === "info"
          ? "size-2.5 rounded-sm bg-info/70"
          : tone === "accent"
            ? "size-2.5 rounded-sm bg-accent-start/80"
            : tone === "good"
              ? "size-2.5 rounded-sm bg-good/60"
              : "size-2.5 rounded-sm bg-warn/60"
      } />
      <span className="kicker text-[10px]">{label}</span>
      <span className="ml-auto text-xs font-mono numeric text-text-dim">
        {compact(total)}
      </span>
    </div>
  );
}

function EmptyTokens() {
  return (
    <p className="text-sm text-text-dim py-3">
      No token usage in this window. Run a session — the next sync tick will pick it up.
    </p>
  );
}

// =============================================================================
// CacheEfficiencyCard
// =============================================================================

export function CacheEfficiencyCard() {
  const [range, setRange] = useState<Range>("7d");
  const { data, isLoading } = useUsageCache(range);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1">
            <CardKicker>Cache hit rate</CardKicker>
            <CardTitle>
              {data ? `${(data.overall_hit_rate * 100).toFixed(1)}%` : "—"}
              <span className="text-text-dim text-sm font-normal ml-2">target 70%+</span>
            </CardTitle>
            <CardDescription>
              <span className="font-mono">cache_read / (input + cache_read + cache_create)</span>
            </CardDescription>
          </div>
          <RangePicker value={range} onChange={setRange} />
        </div>
      </CardHeader>
      {isLoading || !data ? (
        <CardSkeleton lines={3} />
      ) : (
        <>
          {data.low_sample ? (
            <Badge tone="warn">low sample · &lt; 10K billable tokens</Badge>
          ) : null}
          {data.daily.length === 0 ? (
            <p className="text-sm text-text-dim mt-2">No cache activity in this window.</p>
          ) : (
            <Sparkline points={data.daily.map((d) => d.hit_rate)} target={data.target} />
          )}
        </>
      )}
    </Card>
  );
}

function Sparkline({ points, target }: { points: number[]; target: number }) {
  const w = 100; // viewBox width
  const h = 36;
  const path = points
    .map((p, i) => {
      const x = (i / Math.max(1, points.length - 1)) * w;
      const y = h - p * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const targetY = h - target * h;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="mt-3 w-full h-16"
      role="img"
      aria-label="Cache hit-rate trend"
    >
      <line
        x1={0}
        x2={w}
        y1={targetY}
        y2={targetY}
        strokeDasharray="2 2"
        stroke="currentColor"
        className="text-good/40"
        strokeWidth={0.6}
      />
      <path d={path} fill="none" stroke="currentColor" strokeWidth={1.6} className="text-accent-start" />
      {points.length > 0 ? (
        <circle
          cx={w}
          cy={h - points[points.length - 1] * h}
          r={1.6}
          className="text-accent-start"
          fill="currentColor"
        />
      ) : null}
      <rect
        x={0}
        y={0}
        width={w}
        height={h}
        fill="url(#cache-grad)"
        opacity={0.16}
      />
      <defs>
        <linearGradient id="cache-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" className="text-accent-start" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
      <text
        x={2}
        y={h - target * h - 1}
        className="fill-good text-[3px] font-mono"
      >
        {(target * 100).toFixed(0)}%
      </text>
    </svg>
  );
}
