/**
 * LiveSessionsCard + LiveSessionDetail (slide-out drawer).
 *
 * The drawer streams the JSONL tail via SSE so we can show tool-call
 * timeline in real time. Stream-mode sessions get a follow-up box
 * because the dispatcher's stdin is wired to the queue file.
 */

import { useEffect, useRef, useState } from "react";
import { Activity, Clock, Send } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardKicker, CardTitle, CardSkeleton, CardDescription } from "@/components/ui/Card";
import { Sheet } from "@/components/ui/Sheet";
import { StatePill } from "@/components/ui/StatePill";
import { useLiveSessions, useSession, useSystemMutations } from "@/hooks/useQueries";
import { compact, dur, rel } from "@/lib/format";

export function LiveSessionsCard() {
  const { data, isLoading } = useLiveSessions();
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <>
      <Card>
        <CardHeader>
          <CardKicker>Live sessions</CardKicker>
          <CardTitle>What's running right now</CardTitle>
          <CardDescription>
            Sessions whose last tool call landed in the past 5 minutes.
          </CardDescription>
        </CardHeader>
        {isLoading ? (
          <CardSkeleton lines={3} />
        ) : !data || data.items.length === 0 ? (
          <EmptyLive />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {data.items.map((s) => (
              <li key={s.session_id}>
                <button
                  type="button"
                  onClick={() => setOpenId(s.session_id)}
                  className="w-full text-left py-3 grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-4 hover:bg-surface-2/50 rounded-md px-2 -mx-2"
                >
                  <StatePill
                    state="active"
                    pulsing
                    label={(s.live_state ?? "active").replace(/_/g, " ")}
                  />
                  <div className="min-w-0">
                    <div className="text-sm text-text truncate">
                      {s.title ?? <span className="text-text-subtle">untitled</span>}
                    </div>
                    <div className="text-xs text-text-dim font-mono truncate">
                      {(s.cwd ?? "")
                        .replace(/^\/Users\/[^/]+/, "~")} · {s.git_branch ?? "—"} · {s.model ?? "—"}
                    </div>
                  </div>
                  <Badge tone="neutral" numeric>
                    {compact(s.total_tokens)} tok
                  </Badge>
                  <span className="text-xs text-text-subtle">{rel(s.last_tool_ts ?? s.started_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <LiveSessionDetail
        sessionId={openId}
        onClose={() => setOpenId(null)}
      />
    </>
  );
}

function EmptyLive() {
  return (
    <div className="text-sm text-text-dim flex items-center gap-3 py-4">
      <Activity className="size-4 text-text-subtle" />
      No sessions are streaming right now. New sessions appear here within ~5
      seconds; older sessions roll off after 5 minutes of inactivity.
    </div>
  );
}

// -----------------------------------------------------------------------------
// Slide-out drawer
// -----------------------------------------------------------------------------

interface DetailProps {
  sessionId: string | null;
  onClose: () => void;
}

export function LiveSessionDetail({ sessionId, onClose }: DetailProps) {
  const { data, isLoading } = useSession(sessionId);
  const open = sessionId !== null;
  const { sendLiveMessage } = useSystemMutations();
  const [followup, setFollowup] = useState("");
  // Live sessions don't carry an execution_mode (it isn't synced into the
  // sessions table), so the stream-only follow-up affordance stays disabled.
  // Wire this up if/when live stream sessions are actually distinguished.
  const isStream = false;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={data?.session.title || "Session"}
      description={
        data ? (
          <span className="font-mono numeric">
            {(data.session.cwd ?? "")
              .replace(/^\/Users\/[^/]+/, "~")} · {data.session.model ?? "—"}
          </span>
        ) : null
      }
      width={520}
    >
      {isLoading || !data ? (
        <CardSkeleton lines={6} />
      ) : (
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Stat label="started" value={rel(data.session.started_at)} />
            <Stat label="tokens" value={compact(data.session.total_tokens)} />
            <Stat
              label="effective"
              value={compact(data.session.effective_tokens)}
            />
            <Stat label="errors" value={String(data.session.error_count ?? 0)} />
            <Stat
              label="duration"
              value={dur(data.session.duration_ms ?? null)}
            />
            <Stat label="stop" value={data.session.stop_reason || "—"} />
          </div>

          <section>
            <CardKicker>Tool timeline</CardKicker>
            {data.tool_calls.length === 0 ? (
              <p className="mt-2 text-xs text-text-dim">No tool calls recorded yet.</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-2">
                {data.tool_calls.slice(-30).map((t) => (
                  <li
                    key={t.tool_use_id}
                    className="flex items-center gap-3 text-xs font-mono numeric"
                  >
                    <Clock className="size-3 text-text-subtle" />
                    <span className="text-text-dim w-20 truncate">{t.ts.slice(11, 19)}</span>
                    <span className="text-text flex-1 truncate">{t.tool_name}</span>
                    <span className="text-text-dim">{dur(t.duration_ms ?? null)}</span>
                    {t.error ? <Badge tone="bad">err</Badge> : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {isStream ? (
            <FollowupBox
              onSend={async (body) => {
                if (!sessionId) return;
                await sendLiveMessage.mutateAsync({ id: sessionId, body });
                setFollowup("");
              }}
              value={followup}
              onChange={setFollowup}
              loading={sendLiveMessage.isPending}
            />
          ) : (
            <p className="text-xs text-text-subtle border border-dashed border-border rounded-md p-3">
              Read-only — this task was queued as One-shot. Re-queue as
              Interactive to reply from the dashboard.
            </p>
          )}
        </div>
      )}
    </Sheet>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="kicker text-[10px]">{label}</span>
      <span className="text-text font-mono numeric">{value}</span>
    </div>
  );
}

function FollowupBox({
  value,
  onChange,
  onSend,
  loading,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: (v: string) => void;
  loading: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.style.height = "auto";
  }, [value]);
  return (
    <div className="border border-border rounded-lg bg-surface-2/40 p-3 flex flex-col gap-2">
      <CardKicker>Follow up</CardKicker>
      <textarea
        ref={ref}
        rows={3}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Send a message into the running session…"
        className="w-full bg-transparent border-0 text-sm placeholder:text-text-subtle resize-none outline-none"
      />
      <div className="flex items-center justify-end gap-2">
        <Button
          size="sm"
          variant="primary"
          loading={loading}
          disabled={!value.trim()}
          onClick={() => value.trim() && onSend(value.trim())}
        >
          <Send className="size-3.5" /> Send
        </Button>
      </div>
    </div>
  );
}
