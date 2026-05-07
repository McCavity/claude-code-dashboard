import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useEffect, useId, useState, type PropsWithChildren, type ReactNode } from "react";
import { cn } from "@/lib/cn";

interface CollapsibleSectionProps {
  /** Stable id for localStorage persistence. */
  id: string;
  title: string;
  subtitle?: string;
  /** Right-aligned summary chip / count, visible whether open or closed. */
  summary?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}

const STORAGE_PREFIX = "cc:section:";

function readStored(id: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + id);
    if (raw === "1") return true;
    if (raw === "0") return false;
  } catch {
    // SSR / privacy mode — fall back.
  }
  return fallback;
}

function writeStored(id: string, open: boolean) {
  try {
    localStorage.setItem(STORAGE_PREFIX + id, open ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function CollapsibleSection({
  id,
  title,
  subtitle,
  summary,
  defaultOpen = true,
  className,
  children,
}: PropsWithChildren<CollapsibleSectionProps>) {
  const [open, setOpen] = useState(() => readStored(id, defaultOpen));
  const headingId = useId();
  const panelId = useId();

  useEffect(() => {
    writeStored(id, open);
  }, [id, open]);

  return (
    <section className={cn("flex flex-col gap-3", className)}>
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex items-center gap-2 group rounded-md px-1 py-0.5",
            "hover:bg-surface-2/40 transition-colors",
          )}
        >
          <ChevronRight
            className={cn(
              "size-4 text-text-subtle transition-transform duration-200",
              open ? "rotate-90" : "rotate-0",
            )}
          />
          <span id={headingId} className="kicker">
            {title}
          </span>
        </button>
        {subtitle ? (
          <span className="text-sm text-text-dim">{subtitle}</span>
        ) : null}
        {summary ? <span className="ml-auto">{summary}</span> : null}
      </header>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={panelId}
            role="region"
            aria-labelledby={headingId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-4 pt-1">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}
