import { useNavigate } from "@tanstack/react-router";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, Boxes, Command as CommandIcon, Plus, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { useSystemMutations } from "@/hooks/useQueries";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Either navigate or invoke. */
  to?: string;
  invoke?: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onQueueTask: () => void;
}

export function CommandPalette({ open, onClose, onQueueTask }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { manualSync } = useSystemMutations();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);

  const items: CommandItem[] = useMemo(() => {
    return [
      { id: "go-command", label: "Go to Command", icon: CommandIcon, to: "/" },
      { id: "go-activity", label: "Go to Activity", icon: Activity, to: "/activity" },
      { id: "go-skills", label: "Go to Skills & MCP", icon: Boxes, to: "/skills" },
      {
        id: "queue-task",
        label: "Queue a task…",
        hint: "Open the task composer",
        icon: Plus,
        invoke: onQueueTask,
      },
      {
        id: "manual-sync",
        label: "Run JSONL sync now",
        hint: "Re-scan ~/.claude/projects",
        icon: RefreshCw,
        invoke: () => {
          manualSync.mutate();
        },
      },
    ];
  }, [manualSync, onQueueTask]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((i) => i.label.toLowerCase().includes(needle));
  }, [items, q]);

  // Reset highlight + query whenever the palette reopens.
  useEffect(() => {
    if (open) {
      setQ("");
      setHi(0);
      const t = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(t);
    }
    return;
  }, [open]);

  // Keep highlight in range when filtered list shrinks.
  useEffect(() => {
    setHi((h) => Math.min(h, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  // Esc to close, ⌘K from anywhere is wired in __root.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (typeof document === "undefined") return null;

  const run = (item: CommandItem) => {
    onClose();
    if (item.invoke) item.invoke();
    if (item.to) navigate({ to: item.to });
  };

  return createPortal(
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-label="Command palette"
            aria-modal="true"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="fixed left-1/2 top-[18vh] z-50 -translate-x-1/2 w-full max-w-xl px-4"
          >
            <div className="rounded-2xl border border-border bg-surface shadow-glow overflow-hidden">
              <div className="flex items-center gap-3 px-4 h-12 border-b border-border">
                <Search className="size-4 text-text-subtle" />
                <input
                  ref={inputRef}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setHi((h) => Math.min(h + 1, filtered.length - 1));
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setHi((h) => Math.max(h - 1, 0));
                    } else if (e.key === "Enter") {
                      e.preventDefault();
                      const item = filtered[hi];
                      if (item) run(item);
                    }
                  }}
                  placeholder="Search pages, queue a task, run sync…"
                  className="flex-1 bg-transparent outline-none text-sm placeholder:text-text-subtle"
                />
                <kbd className="font-mono text-[10px] text-text-subtle">esc</kbd>
              </div>
              <ul role="listbox" className="max-h-[60vh] overflow-y-auto py-1">
                {filtered.length === 0 ? (
                  <li className="px-4 py-6 text-center text-sm text-text-subtle">No matches</li>
                ) : (
                  filtered.map((item, i) => (
                    <li key={item.id} role="option" aria-selected={i === hi}>
                      <button
                        type="button"
                        onMouseEnter={() => setHi(i)}
                        onClick={() => run(item)}
                        className={cn(
                          "w-full flex items-center gap-3 px-4 py-2 text-left text-sm",
                          i === hi ? "bg-surface-2 text-text" : "text-text-dim",
                        )}
                      >
                        <item.icon className="size-4 text-text-subtle" />
                        <span className="flex-1">{item.label}</span>
                        {item.hint ? (
                          <span className="text-xs text-text-subtle">{item.hint}</span>
                        ) : null}
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
