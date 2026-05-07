import { cn } from "@/lib/cn";
import { useId, useRef, useState, type PropsWithChildren, type ReactNode } from "react";

interface TooltipProps {
  content: ReactNode;
  delay?: number;
  /** Side relative to trigger. Default `top`. */
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}

const SIDE: Record<NonNullable<TooltipProps["side"]>, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

export function Tooltip({
  content,
  delay = 200,
  side = "top",
  className,
  children,
}: PropsWithChildren<TooltipProps>) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const t = useRef<number | null>(null);

  const show = () => {
    if (t.current) window.clearTimeout(t.current);
    t.current = window.setTimeout(() => setOpen(true), delay);
  };
  const hide = () => {
    if (t.current) window.clearTimeout(t.current);
    setOpen(false);
  };

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span aria-describedby={open ? id : undefined}>{children}</span>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className={cn(
            "absolute z-50 max-w-xs whitespace-pre-wrap pointer-events-none",
            "rounded-md border border-border bg-surface-2 px-2 py-1",
            "text-xs text-text shadow-card",
            "animate-fade-in",
            SIDE[side],
            className,
          )}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
