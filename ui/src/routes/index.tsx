import { createFileRoute } from "@tanstack/react-router";
import { CommandPage } from "@/components/panels/CommandPage";

export const Route = createFileRoute("/")({
  component: CommandPage,
});
