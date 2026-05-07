import { cn } from "@/lib/cn";
import type { HTMLAttributes, PropsWithChildren } from "react";

type Tone = "neutral" | "good" | "warn" | "bad" | "info" | "accent";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  /** Render in monospace, tabular numerals — for counts and durations. */
  numeric?: boolean;
}

const TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text-dim border-border",
  good: "bg-good/10 text-good border-good/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  bad: "bg-bad/10 text-bad border-bad/30",
  info: "bg-info/10 text-info border-info/30",
  accent: "bg-accent-start/10 text-accent-start border-accent-start/30",
};

export function Badge({ className, tone = "neutral", numeric, children, ...rest }: PropsWithChildren<BadgeProps>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full",
        "border text-[11px] font-medium",
        numeric && "font-mono numeric",
        TONE[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
