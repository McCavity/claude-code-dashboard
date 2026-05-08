import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useRef, type PropsWithChildren, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  /** Width of the slide-out. Defaults to `460px`. */
  width?: number;
  side?: "right" | "left";
  className?: string;
}

export function Sheet({
  open,
  onClose,
  title,
  description,
  width = 460,
  side = "right",
  className,
  children,
}: PropsWithChildren<SheetProps>) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") trapTab(ref.current, e);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-40 bg-[rgba(21,44,69,0.55)]"
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            ref={ref}
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === "string" ? title : undefined}
            initial={{ x: side === "right" ? width : -width }}
            animate={{ x: 0 }}
            exit={{ x: side === "right" ? width : -width }}
            transition={{ type: "spring", stiffness: 350, damping: 32 }}
            className={cn(
              "fixed top-0 bottom-0 z-50 bg-surface border-l border-border shadow-2xl",
              side === "right" ? "right-0" : "left-0 border-r border-l-0",
              "flex flex-col",
              className,
            )}
            style={{ width }}
          >
            <header className="flex items-start justify-between gap-3 border-b border-border px-6 py-4">
              <div className="flex flex-col gap-0.5">
                {title ? <h2 className="text-base font-semibold text-text">{title}</h2> : null}
                {description ? (
                  <p className="text-xs text-text-dim">{description}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md p-1 text-text-dim hover:text-text hover:bg-surface-2"
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </header>
            <div className="flex-1 overflow-y-auto px-6 py-4">{children}</div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}

function trapTab(root: HTMLElement | null, e: KeyboardEvent) {
  if (!root) return;
  const focusables = root.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
  );
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    last.focus();
    e.preventDefault();
  } else if (!e.shiftKey && document.activeElement === last) {
    first.focus();
    e.preventDefault();
  }
}
