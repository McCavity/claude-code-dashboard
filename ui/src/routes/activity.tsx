import { createFileRoute } from "@tanstack/react-router";
import { ActivityPage } from "@/components/panels/ActivityPage";

export const Route = createFileRoute("/activity")({
  component: ActivityPage,
});
