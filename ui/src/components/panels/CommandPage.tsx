/**
 * Command page — the main dashboard.
 *
 * Always-visible at the top:
 *   - SystemHealthStrip
 *   - KpiRow
 *   - AttentionBar
 *
 * Then collapsible sections (each panel polls on its own cadence):
 *   - Live sessions
 *   - Token usage
 *   - Observability      (8 cards in 2-col grid + PressurePanel full-width)
 *   - HITL               (Decisions + Inbox)
 *   - Mission Control    (TaskBoard + Schedules)
 *   - EmergencyStopBanner
 */

import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { LiveSessionsCard } from "@/components/panels/live";
import {
  AgentFanoutCard,
  EditAcceptanceCard,
  HookActivityCard,
  PressurePanel,
  ProductivityCard,
  ProjectBreakdownCard,
  SessionOutcomesCard,
  ToolLatencyCard,
} from "@/components/panels/observability";
import { DecisionsCard, InboxCard } from "@/components/panels/hitl";
import { SchedulesCard, TaskBoard } from "@/components/panels/mission";
import {
  AttentionBar,
  EmergencyStopBanner,
  KpiRow,
  SystemHealthStrip,
} from "@/components/panels/system";
import { CacheEfficiencyCard, TokenUsageCard } from "@/components/panels/usage";

export function CommandPage() {
  return (
    <div className="flex flex-col gap-6">
      <SystemHealthStrip />
      <KpiRow />
      <AttentionBar />

      <CollapsibleSection id="live" title="Live sessions" defaultOpen>
        <LiveSessionsCard />
      </CollapsibleSection>

      <CollapsibleSection id="usage" title="Token usage" defaultOpen>
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <TokenUsageCard />
          <CacheEfficiencyCard />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        id="observability"
        title="Observability"
        subtitle="latency · errors · cache · sessions"
        defaultOpen
      >
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <SessionOutcomesCard />
          <ToolLatencyCard />
        </div>
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <HookActivityCard />
          <ProjectBreakdownCard />
        </div>
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <AgentFanoutCard />
          <EditAcceptanceCard />
        </div>
        <ProductivityCard />
        <PressurePanel />
      </CollapsibleSection>

      <CollapsibleSection id="hitl" title="Human-in-the-loop">
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 [&>*]:h-full">
          <DecisionsCard />
          <InboxCard />
        </div>
      </CollapsibleSection>

      <CollapsibleSection id="mission" title="Mission Control">
        <TaskBoard />
        <SchedulesCard />
      </CollapsibleSection>

      <EmergencyStopBanner />
    </div>
  );
}
