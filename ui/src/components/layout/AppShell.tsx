import { Link, useRouterState } from "@tanstack/react-router";
import { Activity, Boxes, Command as CommandIcon, Compass } from "lucide-react";
import type { PropsWithChildren } from "react";
import { cn } from "@/lib/cn";

const NAV: Array<{ to: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { to: "/", label: "Command", icon: CommandIcon },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/skills", label: "Skills & MCP", icon: Boxes },
];

export function AppShell({ onOpenPalette, children }: PropsWithChildren<{ onOpenPalette: () => void }>) {
  const path = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-border bg-bg">
        <div className="mx-auto max-w-[1480px] flex items-center gap-6 px-6 py-3">
          <Link
            to="/"
            className="flex items-center gap-2.5 text-text-heading"
            aria-label="Command Centre"
          >
            <span
              className="size-8 rounded-md inline-flex items-center justify-center bg-surface border border-border-glow"
              aria-hidden
            >
              <Compass className="size-4 text-warm" strokeWidth={1.5} />
            </span>
            <span className="font-display italic text-[18px] leading-none">
              Command Centre
            </span>
          </Link>
          <nav className="flex items-center gap-1" aria-label="Primary">
            {NAV.map((item) => {
              const active = item.to === "/" ? path === "/" : path.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex items-center gap-2 px-3 h-9 text-sm rounded transition-colors duration-150 ease-vuz-out",
                    active
                      ? "bg-surface-2 text-text-heading border border-border"
                      : "text-text-dim hover:text-text hover:bg-surface-2/60",
                  )}
                >
                  <item.icon className="size-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto">
            <button
              type="button"
              onClick={onOpenPalette}
              className="flex items-center gap-2 h-9 px-3 rounded border border-border bg-surface text-text-dim hover:text-text hover:border-border-glow text-xs transition-colors duration-150 ease-vuz-out"
            >
              <span>Press</span>
              <kbd className="font-mono px-1.5 py-0.5 rounded-sm bg-surface-2 border border-border text-[10px]">⌘K</kbd>
              <span>to jump</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1480px] px-6 py-6">{children}</main>
      <footer className="px-6 py-6 text-xs text-text-subtle text-center">
        Local · No cloud · {new Date().toLocaleDateString()}
      </footer>
    </div>
  );
}
