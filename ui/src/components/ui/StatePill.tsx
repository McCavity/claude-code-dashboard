import { cn } from "@/lib/cn";

type State = "idle" | "active" | "warning" | "error" | "unknown";

interface StatePillProps {
  state: State;
  label?: string;
  /** Pulsing dot for "currently happening" states. */
  pulsing?: boolean;
}

const COLORS: Record<State, string> = {
  idle: "bg-text-subtle/60",
  active: "bg-good shadow-[0_0_10px_rgba(16,185,129,0.65)]",
  warning: "bg-warn shadow-[0_0_10px_rgba(245,158,11,0.55)]",
  error: "bg-bad shadow-[0_0_10px_rgba(239,68,68,0.55)]",
  unknown: "bg-text-subtle/40",
};

export function StatePill({ state, label, pulsing }: StatePillProps) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-text-dim">
      <span className="relative inline-flex size-2">
        {pulsing && state === "active" ? (
          <span className="absolute inset-0 rounded-full bg-good/50 animate-ping" />
        ) : null}
        <span className={cn("relative inline-flex size-2 rounded-full", COLORS[state])} />
      </span>
      {label ?? state}
    </span>
  );
}
