import { cn } from "@/lib/cn";
import type { HTMLAttributes, PropsWithChildren } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds a subtle accent glow on hover. Use for interactive cards. */
  interactive?: boolean;
}

export function Card({ className, interactive, ...rest }: PropsWithChildren<CardProps>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface shadow-paper animate-fade-in",
        "px-6 py-5",
        interactive && "transition-shadow duration-200 ease-vuz-out hover:shadow-card",
        className,
      )}
      {...rest}
    />
  );
}

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col gap-1 mb-4", className)}
      {...rest}
    />
  );
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "font-display italic text-[22px] leading-[1.15] text-text-heading",
        className,
      )}
      {...rest}
    />
  );
}

export function CardKicker({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("kicker", className)} {...rest} />;
}

export function CardDescription({ className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-sm text-text-dim", className)}
      {...rest}
    />
  );
}

export function CardContent({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-3", className)} {...rest} />;
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mt-4 pt-3 border-t border-border flex items-center gap-2", className)}
      {...rest}
    />
  );
}

/** Skeleton row used while a card loads. Default height suits one
 *  paragraph of text. Set `lines` for more. */
export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton h-3"
          style={{ width: `${80 - (i * 8) % 50}%` }}
        />
      ))}
    </div>
  );
}
