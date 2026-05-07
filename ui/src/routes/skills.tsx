import { createFileRoute } from "@tanstack/react-router";
import { SkillsPage } from "@/components/panels/SkillsPage";

export const Route = createFileRoute("/skills")({
  component: SkillsPage,
});
