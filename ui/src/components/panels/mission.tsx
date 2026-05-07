/**
 * Mission Control panels: task board + composer, schedules + composer.
 *
 * The composers live as slide-out Sheets. Both expose a "default
 * Interactive" execution mode because the dispatcher's stream pipeline
 * unlocks DECISION:/INBOX: markers and live follow-up.
 */

import { Calendar, ChevronDown, Clock, Pencil, Play, Plus, Repeat, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardKicker, CardSkeleton, CardTitle } from "@/components/ui/Card";
import { Sheet } from "@/components/ui/Sheet";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  useScheduleMutations,
  useSchedules,
  useScheduleRuns,
  useTaskMutations,
  useTasks,
  useSkills,
} from "@/hooks/useQueries";
import { cronToHuman, dur, rel } from "@/lib/format";
import type { Task } from "@/lib/api";

// =============================================================================
// TaskBoard
// =============================================================================

export function TaskBoard() {
  const { data, isLoading } = useTasks();
  const { approve, rerun, remove, triggerDispatcher } = useTaskMutations();
  const [composerOpen, setComposerOpen] = useState(false);

  const groups = useMemo(() => {
    const g: { pending: Task[]; running: Task[]; done: Task[] } = {
      pending: [],
      running: [],
      done: [],
    };
    if (!data) return g;
    for (const t of data.items) {
      if (t.status === "running") g.running.push(t);
      else if (t.status === "done") g.done.push(t);
      else g.pending.push(t);
    }
    return g;
  }, [data]);

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <CardKicker>Mission Control</CardKicker>
              <CardTitle>Task board</CardTitle>
              <CardDescription>
                Approvals, runs, and dispositions. Dispatcher tick: every 120 s.
                Use the trigger button to run now.
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="secondary"
              loading={triggerDispatcher.isPending}
              onClick={() => triggerDispatcher.mutate()}
            >
              <Play className="size-3.5" /> Trigger dispatcher
            </Button>
            <Button size="sm" variant="primary" onClick={() => setComposerOpen(true)}>
              <Plus className="size-3.5" /> New task
            </Button>
          </div>
        </CardHeader>
        {isLoading ? (
          <CardSkeleton lines={4} />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Column title="Pending" tone="info" tasks={groups.pending} onApprove={(id) => approve.mutate(id)} onDelete={(id) => remove.mutate(id)} />
            <Column title="Running" tone="accent" tasks={groups.running} onDelete={(id) => remove.mutate(id)} />
            <Column title="Done & failed" tone="neutral" tasks={groups.done} onRerun={(id) => rerun.mutate(id)} onDelete={(id) => remove.mutate(id)} />
          </div>
        )}
      </Card>
      <TaskComposer open={composerOpen} onClose={() => setComposerOpen(false)} />
    </>
  );
}

function Column({
  title,
  tone,
  tasks,
  onApprove,
  onRerun,
  onDelete,
}: {
  title: string;
  tone: "info" | "accent" | "neutral";
  tasks: Task[];
  onApprove?: (id: number) => void;
  onRerun?: (id: number) => void;
  onDelete?: (id: number) => void;
}) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Badge tone={tone}>{title}</Badge>
        <span className="text-xs text-text-subtle font-mono numeric">
          {tasks.length}
        </span>
      </div>
      {tasks.length === 0 ? (
        <p className="text-xs text-text-subtle italic px-1 py-2">empty</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {tasks.map((t) => (
            <li
              key={t.id}
              className="rounded-lg border border-border bg-surface-2/40 p-3 flex flex-col gap-2"
            >
              <div className="flex items-start gap-2">
                <span className="text-sm text-text font-medium flex-1 line-clamp-2">{t.title}</span>
                <span className="text-[11px] text-text-subtle font-mono">#{t.id}</span>
              </div>
              {t.description ? (
                <p className="text-xs text-text-dim line-clamp-2">{t.description}</p>
              ) : null}
              <div className="flex items-center gap-1.5 flex-wrap">
                <StatusBadge status={t.status} />
                {t.assigned_skill ? (
                  <Badge tone="accent">{t.assigned_skill}</Badge>
                ) : null}
                {t.execution_mode === "stream" ? <Badge tone="info">interactive</Badge> : null}
                {t.dry_run ? <Badge tone="warn">dry-run</Badge> : null}
                {t.risk_level !== "low" ? (
                  <Badge tone={t.risk_level === "high" ? "bad" : "warn"}>
                    risk {t.risk_level}
                  </Badge>
                ) : null}
                {t.duration_ms ? (
                  <span className="text-[11px] text-text-subtle font-mono">{dur(t.duration_ms)}</span>
                ) : null}
              </div>
              {t.error_message ? (
                <p className="text-xs text-bad/90 line-clamp-2">{t.error_message}</p>
              ) : t.output_summary ? (
                <p className="text-xs text-text-dim line-clamp-3">{t.output_summary}</p>
              ) : null}
              <div className="flex items-center gap-1.5 mt-1">
                {t.status === "awaiting_approval" && onApprove ? (
                  <Button size="sm" variant="primary" onClick={() => onApprove(t.id)}>
                    Approve
                  </Button>
                ) : null}
                {t.status === "failed" && onRerun ? (
                  <Button size="sm" variant="secondary" onClick={() => onRerun(t.id)}>
                    <Repeat className="size-3.5" /> Rerun
                  </Button>
                ) : null}
                {onDelete ? (
                  <Button size="sm" variant="ghost" onClick={() => onDelete(t.id)}>
                    <Trash2 className="size-3.5" />
                  </Button>
                ) : null}
                <span className="ml-auto text-[10px] text-text-subtle font-mono">
                  {rel(t.created_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: Task["status"] }) {
  const map: Record<Task["status"], { tone: "info" | "accent" | "good" | "warn" | "bad" | "neutral"; label: string }> = {
    pending: { tone: "info", label: "pending" },
    awaiting_approval: { tone: "warn", label: "awaiting approval" },
    running: { tone: "accent", label: "running" },
    done: { tone: "good", label: "done" },
    failed: { tone: "bad", label: "failed" },
    cancelled: { tone: "neutral", label: "cancelled" },
  };
  const m = map[status];
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

// =============================================================================
// TaskComposer
// =============================================================================

interface TaskComposerProps {
  open: boolean;
  onClose: () => void;
}

export function TaskComposer({ open, onClose }: TaskComposerProps) {
  const { create } = useTaskMutations();
  const { data: skillsData } = useSkills();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [model, setModel] = useState("");
  const [executionMode, setExecutionMode] = useState<"stream" | "classic">("stream");
  const [priority, setPriority] = useState(50);
  const [quadrant, setQuadrant] = useState<Task["quadrant"]>("do");
  const [riskLevel, setRiskLevel] = useState<Task["risk_level"]>("low");
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [skill, setSkill] = useState("");

  const reset = () => {
    setTitle("");
    setDescription("");
    setModel("");
    setExecutionMode("stream");
    setPriority(50);
    setQuadrant("do");
    setRiskLevel("low");
    setRequiresApproval(false);
    setDryRun(false);
    setSkill("");
  };

  const submit = async () => {
    if (!title.trim()) return;
    await create.mutateAsync({
      title: title.trim(),
      description: description.trim() || undefined,
      model: model || undefined,
      execution_mode: executionMode,
      priority,
      quadrant,
      risk_level: riskLevel,
      requires_approval: requiresApproval,
      dry_run: dryRun,
      assigned_skill: skill || undefined,
    });
    reset();
    onClose();
  };

  return (
    <Sheet
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Queue a task"
      description="The dispatcher will pick this up on its next 120s tick, sooner if you trigger manually."
      width={520}
    >
      <div className="flex flex-col gap-4">
        <Field label="Title" required>
          <input
            autoFocus
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What should the agent do?"
            className="w-full rounded-lg bg-surface-2 border border-border p-2.5 text-sm placeholder:text-text-subtle outline-none focus:border-accent-start"
          />
        </Field>
        <Field label="Description" hint="Optional. Markdown OK.">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Context, constraints, success criteria…"
            className="w-full rounded-lg bg-surface-2 border border-border p-2.5 text-sm placeholder:text-text-subtle outline-none focus:border-accent-start"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Mode">
            <div className="flex flex-col gap-1.5">
              {(["stream", "classic"] as const).map((m) => (
                <label
                  key={m}
                  className={`flex items-start gap-2 rounded-md border p-2 text-xs cursor-pointer ${
                    executionMode === m ? "border-accent-start bg-accent-start/10" : "border-border bg-surface-2/40"
                  }`}
                >
                  <input
                    type="radio"
                    name="mode"
                    checked={executionMode === m}
                    onChange={() => setExecutionMode(m)}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-text">{m === "stream" ? "Interactive" : "One-shot"}</div>
                    <div className="text-text-subtle text-[10px]">
                      {m === "stream"
                        ? "Reply mid-run from the dashboard"
                        : "Fire and forget — no back-and-forth"}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </Field>
          <Field label="Skill" hint="Leave blank to let skill_router pick">
            <select
              value={skill}
              onChange={(e) => setSkill(e.target.value)}
              className="w-full rounded-lg bg-surface-2 border border-border p-2 text-sm outline-none focus:border-accent-start"
            >
              <option value="">— none —</option>
              {skillsData?.items.map((s) => (
                <option key={`${s.environment}:${s.name}`} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Priority">
            <input
              type="number"
              min={0}
              max={100}
              value={priority}
              onChange={(e) => setPriority(parseInt(e.target.value, 10) || 50)}
              className="w-full rounded-lg bg-surface-2 border border-border p-2 text-sm font-mono numeric"
            />
          </Field>
          <Field label="Quadrant">
            <select
              value={quadrant}
              onChange={(e) => setQuadrant(e.target.value as Task["quadrant"])}
              className="w-full rounded-lg bg-surface-2 border border-border p-2 text-sm"
            >
              <option value="do">do</option>
              <option value="schedule">schedule</option>
              <option value="delegate">delegate</option>
              <option value="archive">archive</option>
            </select>
          </Field>
          <Field label="Risk">
            <select
              value={riskLevel}
              onChange={(e) => setRiskLevel(e.target.value as Task["risk_level"])}
              className="w-full rounded-lg bg-surface-2 border border-border p-2 text-sm"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </Field>
        </div>
        <Field label="Model" hint="Override the default; blank = MISSION_CONTROL_DEFAULT_MODEL">
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="claude-sonnet-4-6"
            className="w-full rounded-lg bg-surface-2 border border-border p-2 text-sm font-mono"
          />
        </Field>
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={requiresApproval}
              onChange={(e) => setRequiresApproval(e.target.checked)}
            />
            Require approval before running
          </label>
          <Tooltip content="The dispatcher does not commit, push, or modify files. Useful for risky tasks.">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
              />
              Dry-run
            </label>
          </Tooltip>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="md" onClick={() => { reset(); onClose(); }}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            disabled={!title.trim()}
            loading={create.isPending}
            onClick={submit}
          >
            Queue task
          </Button>
        </div>
      </div>
    </Sheet>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="kicker">
        {label}
        {required ? <span className="text-bad ml-1">*</span> : null}
      </span>
      {children}
      {hint ? <span className="text-[10px] text-text-subtle">{hint}</span> : null}
    </label>
  );
}

// =============================================================================
// SchedulesCard
// =============================================================================

export function SchedulesCard() {
  const { data, isLoading } = useSchedules();
  const { update, remove } = useScheduleMutations();
  const [composerOpen, setComposerOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <CardKicker>Schedules</CardKicker>
              <CardTitle>Recurring tasks</CardTitle>
              <CardDescription>
                {data ? `Times shown in ${data.tz}.` : "Times shown in your local zone."}
              </CardDescription>
            </div>
            <Button size="sm" variant="primary" onClick={() => setComposerOpen(true)}>
              <Plus className="size-3.5" /> New schedule
            </Button>
          </div>
        </CardHeader>
        {isLoading ? (
          <CardSkeleton lines={3} />
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-text-dim flex items-center gap-2">
            <Calendar className="size-4 text-text-subtle" />
            No schedules yet. Set one up — the heartbeat materialises matched
            schedules into ops_tasks.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {data.items.map((s) => {
              const isStale = s.next_run_at && new Date(s.next_run_at).getTime() < Date.now() - 5 * 60_000;
              return (
                <li key={s.id} className="py-3">
                  <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3">
                    <span
                      className={`size-2 rounded-full ${
                        s.enabled ? (isStale ? "bg-warn" : "bg-good") : "bg-text-subtle/50"
                      }`}
                    />
                    <div className="min-w-0">
                      <div className="text-sm text-text">{s.name}</div>
                      <div className="text-[11px] text-text-subtle font-mono">
                        {cronToHuman(s.cron_expression)} · next {rel(s.next_run_at)}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        update.mutate({ id: s.id, body: { enabled: !s.enabled } })
                      }
                    >
                      {s.enabled ? "Disable" : "Enable"}
                    </Button>
                    <button
                      onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
                      className="text-text-subtle hover:text-text p-1"
                      aria-label="Show recent runs"
                    >
                      <ChevronDown
                        className={`size-4 transition-transform ${expandedId === s.id ? "rotate-180" : ""}`}
                      />
                    </button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => remove.mutate(s.id)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                  {expandedId === s.id ? <ScheduleRuns scheduleId={s.id} /> : null}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      <ScheduleComposer open={composerOpen} onClose={() => setComposerOpen(false)} />
    </>
  );
}

function ScheduleRuns({ scheduleId }: { scheduleId: number }) {
  const { data } = useScheduleRuns(scheduleId, 5);
  if (!data || data.items.length === 0) {
    return (
      <p className="ml-6 mt-2 text-xs text-text-subtle italic">No runs materialised yet.</p>
    );
  }
  return (
    <ul className="ml-6 mt-2 flex flex-col gap-1 text-xs">
      {data.items.map((r) => (
        <li key={r.id} className="grid grid-cols-[auto_auto_1fr_auto] gap-2 items-baseline">
          <Clock className="size-3 text-text-subtle" />
          <span className="font-mono text-text-dim numeric">{rel(r.created_at)}</span>
          <span className="text-text-dim truncate">
            {r.error_message ?? r.output_summary ?? "—"}
          </span>
          <Badge tone={r.status === "failed" ? "bad" : r.status === "done" ? "good" : "info"}>
            {r.status}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

// =============================================================================
// ScheduleComposer
// =============================================================================

const DOWS: Array<{ short: string; idx: number }> = [
  { short: "Mon", idx: 0 },
  { short: "Tue", idx: 1 },
  { short: "Wed", idx: 2 },
  { short: "Thu", idx: 3 },
  { short: "Fri", idx: 4 },
  { short: "Sat", idx: 5 },
  { short: "Sun", idx: 6 },
];

interface ComposerProps {
  open: boolean;
  onClose: () => void;
}

export function ScheduleComposer({ open, onClose }: ComposerProps) {
  const { create, parseNL } = useScheduleMutations();
  const { data: skillsData } = useSkills();

  const [name, setName] = useState("");
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState<0 | 15 | 30 | 45>(0);
  const [dows, setDows] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]));
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDesc, setTaskDesc] = useState("");
  const [skill, setSkill] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [nl, setNl] = useState("");

  const cron = useMemo(() => {
    const dowList = [...dows].sort().join(",") || "*";
    return `${minute} ${hour} * * ${dowList}`;
  }, [hour, minute, dows]);

  const reset = () => {
    setName("");
    setHour(9);
    setMinute(0);
    setDows(new Set([0, 1, 2, 3, 4]));
    setTaskTitle("");
    setTaskDesc("");
    setSkill("");
    setEnabled(true);
    setNl("");
  };

  const setEveryDay = () => setDows(new Set([0, 1, 2, 3, 4, 5, 6]));
  const setWeekdays = () => setDows(new Set([0, 1, 2, 3, 4]));
  const setWeekends = () => setDows(new Set([5, 6]));

  const submit = async () => {
    if (!name.trim() || !taskTitle.trim()) return;
    await create.mutateAsync({
      name: name.trim(),
      cron_expression: cron,
      task_title: taskTitle.trim(),
      task_description: taskDesc.trim() || undefined,
      assigned_skill: skill || undefined,
      enabled,
    });
    reset();
    onClose();
  };

  const tryNL = async () => {
    if (!nl.trim()) return;
    try {
      const result = await parseNL.mutateAsync(nl.trim());
      // result.cron is a 5-field cron; parse and apply.
      const parts = result.cron.split(" ");
      if (parts.length === 5) {
        const m = parseInt(parts[0], 10);
        if ([0, 15, 30, 45].includes(m)) setMinute(m as 0 | 15 | 30 | 45);
        const h = parseInt(parts[1], 10);
        if (!Number.isNaN(h) && h >= 0 && h <= 23) setHour(h);
        const dowField = parts[4];
        if (dowField !== "*") {
          const ns = dowField.split(",").map((p) => parseInt(p, 10)).filter((n) => !Number.isNaN(n));
          setDows(new Set(ns));
        }
      }
    } catch {
      /* leave as is */
    }
  };

  return (
    <Sheet
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="New schedule"
      description="Heartbeat materialises matched schedules into ops_tasks."
      width={520}
    >
      <div className="flex flex-col gap-4">
        <Field label="Schedule name" required>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Morning summary"
            className="w-full rounded-lg bg-surface-2 border border-border p-2.5 text-sm outline-none focus:border-accent-start"
          />
        </Field>

        <Field label="Time">
          <div className="flex items-center gap-2">
            <select
              value={hour}
              onChange={(e) => setHour(parseInt(e.target.value, 10))}
              className="rounded-lg bg-surface-2 border border-border p-2 text-sm font-mono"
            >
              {Array.from({ length: 24 }).map((_, i) => (
                <option key={i} value={i}>
                  {i.toString().padStart(2, "0")}
                </option>
              ))}
            </select>
            <span className="text-text-subtle">:</span>
            <select
              value={minute}
              onChange={(e) => setMinute(parseInt(e.target.value, 10) as 0 | 15 | 30 | 45)}
              className="rounded-lg bg-surface-2 border border-border p-2 text-sm font-mono"
            >
              {[0, 15, 30, 45].map((m) => (
                <option key={m} value={m}>
                  {m.toString().padStart(2, "0")}
                </option>
              ))}
            </select>
          </div>
        </Field>

        <Field label="Days">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1 flex-wrap">
              {DOWS.map((d) => {
                const on = dows.has(d.idx);
                return (
                  <button
                    key={d.idx}
                    type="button"
                    onClick={() => {
                      const next = new Set(dows);
                      if (on) next.delete(d.idx);
                      else next.add(d.idx);
                      setDows(next);
                    }}
                    className={`px-2.5 h-8 rounded-md text-xs font-mono ${
                      on
                        ? "bg-accent-start/20 text-accent-start border border-accent-start/40"
                        : "bg-surface-2/40 text-text-dim border border-border"
                    }`}
                  >
                    {d.short}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-1 text-[10px] text-text-subtle">
              <button onClick={setEveryDay} className="hover:text-text">Every day</button>
              <span>·</span>
              <button onClick={setWeekdays} className="hover:text-text">Weekdays</button>
              <span>·</span>
              <button onClick={setWeekends} className="hover:text-text">Weekends</button>
            </div>
          </div>
        </Field>

        <div className="rounded-md border border-border bg-surface-2/40 px-3 py-2 text-xs flex items-center gap-2 font-mono">
          <span className="kicker text-[10px]">cron</span>
          <span className="text-text">{cron}</span>
          <span className="ml-auto text-text-subtle">{cronToHuman(cron)}</span>
        </div>

        <Field label="Natural-language helper" hint="Optional. Calls Haiku via /api/schedules/parse-nl when ANTHROPIC_API_KEY is set.">
          <div className="flex gap-2">
            <input
              value={nl}
              onChange={(e) => setNl(e.target.value)}
              placeholder='e.g. "every weekday at 9am"'
              className="flex-1 rounded-lg bg-surface-2 border border-border p-2.5 text-sm outline-none focus:border-accent-start"
            />
            <Button size="md" variant="secondary" loading={parseNL.isPending} onClick={tryNL}>
              <Pencil className="size-3.5" /> Parse
            </Button>
          </div>
          {parseNL.isError ? (
            <span className="text-bad text-[10px]">{(parseNL.error as Error).message}</span>
          ) : null}
        </Field>

        <Field label="Task title" required>
          <input
            value={taskTitle}
            onChange={(e) => setTaskTitle(e.target.value)}
            placeholder="What should the agent do each time?"
            className="w-full rounded-lg bg-surface-2 border border-border p-2.5 text-sm outline-none focus:border-accent-start"
          />
        </Field>
        <Field label="Task description">
          <textarea
            value={taskDesc}
            onChange={(e) => setTaskDesc(e.target.value)}
            rows={3}
            className="w-full rounded-lg bg-surface-2 border border-border p-2.5 text-sm outline-none focus:border-accent-start"
          />
        </Field>
        <Field label="Skill">
          <select
            value={skill}
            onChange={(e) => setSkill(e.target.value)}
            className="w-full rounded-lg bg-surface-2 border border-border p-2 text-sm"
          >
            <option value="">— none —</option>
            {skillsData?.items.map((s) => (
              <option key={`${s.environment}:${s.name}`} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled
        </label>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="md" onClick={() => { reset(); onClose(); }}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            disabled={!name.trim() || !taskTitle.trim()}
            loading={create.isPending}
            onClick={submit}
          >
            Create
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
