/**
 * Central React Query hooks. Every fetch in the UI goes through one of
 * these so refetch intervals, query keys, and stale times are
 * consistent.
 *
 * Default refetch is 30 s. Hot data (decisions, inbox, attention,
 * live sessions) polls faster so the dashboard reacts quickly.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const POLL_FAST = 5_000;
const POLL_NORMAL = 30_000;
const POLL_SLOW = 60_000;

// =============================================================================
// System / health
// =============================================================================

export const useHealth = () =>
  useQuery({
    queryKey: ["systemHealth"],
    queryFn: api.systemHealth,
    refetchInterval: POLL_FAST,
  });

export const useSummary = () =>
  useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: POLL_NORMAL });

export const useAttention = () =>
  useQuery({
    queryKey: ["attention"],
    queryFn: api.attention,
    refetchInterval: POLL_FAST,
  });

// =============================================================================
// Sessions
// =============================================================================

export const useLiveSessions = () =>
  useQuery({
    queryKey: ["sessionsLive"],
    queryFn: api.sessionsLive,
    refetchInterval: POLL_FAST,
  });

export const useSession = (id: string | null | undefined) =>
  useQuery({
    queryKey: ["sessionDetail", id],
    queryFn: () => api.sessionDetail(id!),
    enabled: Boolean(id),
    refetchInterval: POLL_NORMAL,
  });

export const useSessions = (params: Parameters<typeof api.sessions>[0] = {}) =>
  useQuery({
    queryKey: ["sessions", params],
    queryFn: () => api.sessions(params),
    refetchInterval: POLL_NORMAL,
  });

export const useSessionOutcomes = (range: string) =>
  useQuery({
    queryKey: ["sessionOutcomes", range],
    queryFn: () => api.sessionOutcomes(range),
    refetchInterval: POLL_NORMAL,
  });

export const useSessionsByProject = (range: string) =>
  useQuery({
    queryKey: ["sessionsByProject", range],
    queryFn: () => api.sessionsByProject(range),
    refetchInterval: POLL_NORMAL,
  });

// =============================================================================
// Usage / tools
// =============================================================================

export const useUsageTokens = (range: string) =>
  useQuery({
    queryKey: ["usageTokens", range],
    queryFn: () => api.usageTokens(range),
    refetchInterval: POLL_NORMAL,
  });

export const useUsageCache = (range: string) =>
  useQuery({
    queryKey: ["usageCache", range],
    queryFn: () => api.usageCache(range),
    refetchInterval: POLL_NORMAL,
  });

export const useToolsLatency = (range: string) =>
  useQuery({
    queryKey: ["toolsLatency", range],
    queryFn: () => api.toolsLatency(range),
    refetchInterval: POLL_NORMAL,
  });

export const useAgentFanout = (range: string) =>
  useQuery({
    queryKey: ["agentFanout", range],
    queryFn: () => api.toolsAgentFanout(range),
    refetchInterval: POLL_NORMAL,
  });

export const useEditDecisions = (range: string) =>
  useQuery({
    queryKey: ["editDecisions", range],
    queryFn: () => api.toolsEditDecisions(range),
    refetchInterval: POLL_NORMAL,
  });

export const useHooksActivity = (range: string) =>
  useQuery({
    queryKey: ["hooksActivity", range],
    queryFn: () => api.hooksActivity(range),
    refetchInterval: POLL_NORMAL,
  });

export const useProductivity = (range: string) =>
  useQuery({
    queryKey: ["productivity", range],
    queryFn: () => api.productivity(range),
    refetchInterval: POLL_SLOW,
  });

export const useContextHealth = () =>
  useQuery({
    queryKey: ["contextHealth"],
    queryFn: api.contextHealth,
    refetchInterval: POLL_SLOW,
  });

export const useSkillEconomics = (range: string) =>
  useQuery({
    queryKey: ["skillEconomics", range],
    queryFn: () => api.skillEconomics(range),
    refetchInterval: POLL_SLOW,
  });

export const useFailures = (range: string) =>
  useQuery({
    queryKey: ["failures", range],
    queryFn: () => api.failures(range),
    refetchInterval: POLL_NORMAL,
  });

export const usePressure = (range: string) =>
  useQuery({
    queryKey: ["pressure", range],
    queryFn: () => api.pressure(range),
    refetchInterval: POLL_NORMAL,
  });

// =============================================================================
// MCP / skills
// =============================================================================

export const useMcpOverview = (range: string) =>
  useQuery({
    queryKey: ["mcpOverview", range],
    queryFn: () => api.mcpOverview(range),
    refetchInterval: POLL_SLOW,
  });

export const useMcpTools = (server: string | null, range: string) =>
  useQuery({
    queryKey: ["mcpTools", server, range],
    queryFn: () => api.mcpTools(server!, range),
    enabled: Boolean(server),
    refetchInterval: POLL_NORMAL,
  });

export const useSkills = (params: Parameters<typeof api.skills>[0] = {}) =>
  useQuery({
    queryKey: ["skills", params],
    queryFn: () => api.skills(params),
    refetchInterval: POLL_SLOW,
  });

// =============================================================================
// HITL — decisions / inbox
// =============================================================================

export const useDecisions = (status: "pending" | "answered" | "all" = "pending") =>
  useQuery({
    queryKey: ["decisions", status],
    queryFn: () => api.decisions(status),
    refetchInterval: POLL_FAST,
  });

export const useInbox = (unread = 0) =>
  useQuery({
    queryKey: ["inbox", unread],
    queryFn: () => api.inbox({ unread }),
    refetchInterval: POLL_FAST,
  });

// =============================================================================
// Tasks / schedules
// =============================================================================

export const useTasks = (params: Parameters<typeof api.tasks>[0] = {}) =>
  useQuery({
    queryKey: ["tasks", params],
    queryFn: () => api.tasks(params),
    refetchInterval: POLL_NORMAL,
  });

export const useSchedules = () =>
  useQuery({
    queryKey: ["schedules"],
    queryFn: api.schedules,
    refetchInterval: POLL_NORMAL,
  });

export const useScheduleRuns = (id: number | null, limit = 5) =>
  useQuery({
    queryKey: ["scheduleRuns", id, limit],
    queryFn: () => api.scheduleRuns(id!, limit),
    enabled: id !== null,
    refetchInterval: POLL_NORMAL,
  });

// =============================================================================
// Mutations
// =============================================================================

export const useTaskMutations = () => {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["tasks"] });
  return {
    create: useMutation({ mutationFn: api.createTask, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateTask>[1] }) =>
        api.updateTask(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: api.deleteTask, onSuccess: invalidate }),
    approve: useMutation({ mutationFn: api.approveTask, onSuccess: invalidate }),
    rerun: useMutation({ mutationFn: api.rerunTask, onSuccess: invalidate }),
    triggerDispatcher: useMutation({ mutationFn: api.triggerDispatcher, onSuccess: invalidate }),
  };
};

export const useScheduleMutations = () => {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["schedules"] });
  return {
    create: useMutation({ mutationFn: api.createSchedule, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateSchedule>[1] }) =>
        api.updateSchedule(id, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: api.deleteSchedule, onSuccess: invalidate }),
    parseNL: useMutation({ mutationFn: api.parseScheduleNL }),
  };
};

export const useDecisionMutations = () => {
  const qc = useQueryClient();
  return {
    answer: useMutation({
      mutationFn: ({ id, answer }: { id: number; answer: string }) =>
        api.answerDecision(id, answer),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["decisions"] }),
    }),
  };
};

export const useInboxMutations = () => {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["inbox"] });
  return {
    markRead: useMutation({ mutationFn: api.markInboxRead, onSuccess: invalidate }),
    reply: useMutation({
      mutationFn: ({ id, body }: { id: number; body: string }) => api.replyInbox(id, body),
      onSuccess: invalidate,
    }),
  };
};

export const useSystemMutations = () => {
  const qc = useQueryClient();
  return {
    emergencyStop: useMutation({
      mutationFn: api.emergencyStop,
      onSuccess: () => qc.invalidateQueries(),
    }),
    emergencyResume: useMutation({
      mutationFn: api.emergencyResume,
      onSuccess: () => qc.invalidateQueries(),
    }),
    manualSync: useMutation({ mutationFn: api.manualSync }),
    mcpSync: useMutation({
      mutationFn: api.mcpSync,
      onSuccess: () => qc.invalidateQueries({ queryKey: ["mcpOverview"] }),
    }),
    skillsSync: useMutation({
      mutationFn: api.skillsSync,
      onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
    }),
    setSkillAutonomy: useMutation({
      mutationFn: ({
        name,
        body,
      }: {
        name: string;
        body: Parameters<typeof api.setSkillAutonomy>[1];
      }) => api.setSkillAutonomy(name, body),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
    }),
    sendLiveMessage: useMutation({
      mutationFn: ({ id, body }: { id: string; body: string }) => api.sendLiveMessage(id, body),
    }),
  };
};
