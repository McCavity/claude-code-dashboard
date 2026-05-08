import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const VARIANT: Record<Variant, string> = {
  primary:
    "text-text-heading bg-info shadow-paper hover:bg-accent-start hover:text-bg active:translate-y-px",
  secondary:
    "text-text bg-surface-2 border border-border hover:border-border-glow",
  ghost: "text-text-dim hover:text-text hover:bg-surface-2",
  danger:
    "text-text-heading bg-bad/90 hover:bg-bad shadow-paper active:translate-y-px",
};

const SIZE: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-10 px-5 text-sm",
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  loading,
  disabled,
  children,
  ...rest
}: PropsWithChildren<ButtonProps>) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded font-medium",
        "transition-colors duration-150 ease-vuz-out disabled:opacity-50 disabled:cursor-not-allowed",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-info",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {loading ? <span className="size-3 rounded-full border-2 border-current border-t-transparent animate-spin" /> : null}
      {children}
    </button>
  );
}
