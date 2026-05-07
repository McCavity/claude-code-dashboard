import { Outlet, createRootRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { CommandPalette } from "@/components/layout/CommandPalette";

function RootLayout() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMeta = e.metaKey || e.ctrlKey;
      if (isMeta && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Make the composer signal available to all panels via a custom event.
  useEffect(() => {
    const onTrigger = () => setComposerOpen(true);
    window.addEventListener("cc:openTaskComposer", onTrigger);
    return () => window.removeEventListener("cc:openTaskComposer", onTrigger);
  }, []);

  return (
    <AppShell onOpenPalette={() => setPaletteOpen(true)}>
      <Outlet />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onQueueTask={() => {
          setComposerOpen(true);
          window.dispatchEvent(new CustomEvent("cc:openTaskComposer"));
        }}
      />
      {/* The composer itself lives inside the Mission Control panel and
          listens for the cc:openTaskComposer event. The state above
          mainly drives the keyboard shortcut path. */}
      <span data-composer-bridge data-open={composerOpen ? "1" : "0"} hidden />
    </AppShell>
  );
}

export const Route = createRootRoute({
  component: RootLayout,
});
