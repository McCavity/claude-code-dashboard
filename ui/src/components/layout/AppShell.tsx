import { Link, useRouterState } from "@tanstack/react-router";
import { Activity, Boxes, Command as CommandIcon, Sparkles } from "lucide-react";
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
      <header className="sticky top-0 z-30 border-b border-border bg-bg/80 backdrop-blur-xl">
        <div className="mx-auto max-w-[1480px] flex items-center gap-6 px-6 py-3">
          <Link
            to="/"
            className="flex items-center gap-2 text-text font-semibold tracking-tight"
            aria-label="Command Centre"
          >
            <span className="size-7 rounded-lg bg-gradient-accent inline-flex items-center justify-center shadow-glow">
              <Sparkles className="size-4 text-white" />
            </span>
            <span className="text-sm">Command Centre</span>
          </Link>
          <nav className="flex items-center gap-1" aria-label="Primary">
            {NAV.map((item) => {
              const active = item.to === "/" ? path === "/" : path.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex items-center gap-2 px-3 h-9 text-sm rounded-md",
                    active
                      ? "bg-surface-2 text-text border border-border"
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
              className="flex items-center gap-2 h-9 px-3 rounded-md border border-border bg-surface text-text-dim hover:text-text hover:border-border-glow text-xs"
            >
              <span>Press</span>
              <kbd className="font-mono px-1.5 py-0.5 rounded bg-surface-2 border border-border text-[10px]">⌘K</kbd>
              <span>to jump</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1480px] px-6 py-6">{children}</main>
      <footer className="px-6 py-6 text-xs text-text-subtle text-center">
        Local. No cloud. {new Date().toLocaleDateString()}
      </footer>
    </div>
  );
}
