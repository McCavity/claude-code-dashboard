/**
 * Human-in-the-loop panels: pending decisions and the inbox.
 *
 * Both poll on the fast cadence (5 s) so a `DECISION:` marker emitted by
 * the dispatcher shows up nearly instantly.
 */

import { Inbox, MessageSquareWarning, Send } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardHeader, CardKicker, CardSkeleton, CardTitle } from "@/components/ui/Card";
import { Sheet } from "@/components/ui/Sheet";
import { useDecisionMutations, useDecisions, useInbox, useInboxMutations } from "@/hooks/useQueries";
import { rel } from "@/lib/format";

// =============================================================================
// DecisionsCard
// =============================================================================

export function DecisionsCard() {
  const { data, isLoading } = useDecisions("pending");
  const { answer } = useDecisionMutations();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  const active = data?.items.find((d) => d.id === activeId) ?? null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardKicker>Decisions</CardKicker>
          <CardTitle>Pending HITL questions</CardTitle>
          <CardDescription>
            Each row was a <code className="font-mono">DECISION:</code> marker the dispatcher
            spotted in streaming output. Answer to unblock the run.
          </CardDescription>
        </CardHeader>
        {isLoading ? (
          <CardSkeleton lines={3} />
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-text-dim flex items-center gap-2">
            <MessageSquareWarning className="size-4 text-text-subtle" />
            No decisions waiting. The dispatcher will surface anything urgent here.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {data.items.map((d) => (
              <li
                key={d.id}
                className="py-3 grid grid-cols-[1fr_auto] items-start gap-3"
              >
                <div className="min-w-0">
                  <div className="text-sm text-text line-clamp-2">{d.prompt}</div>
                  <div className="text-[11px] text-text-subtle font-mono mt-0.5">
                    task #{d.task_id ?? "—"} · {rel(d.created_at)}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => {
                    setActiveId(d.id);
                    setDraft("");
                  }}
                >
                  Answer
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Sheet
        open={active !== null}
        onClose={() => setActiveId(null)}
        title="Answer decision"
        description={active ? `task #${active.task_id ?? "—"}` : ""}
      >
        {active ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-text-dim whitespace-pre-wrap border-l-2 border-warn/40 pl-3">
              {active.prompt}
            </p>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={5}
              autoFocus
              placeholder="Your answer — will be injected into the dispatched session's stdin."
              className="w-full rounded-lg bg-surface-2 border border-border p-3 text-sm placeholder:text-text-subtle outline-none focus:border-accent-start"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="md" onClick={() => setActiveId(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="md"
                disabled={!draft.trim()}
                loading={answer.isPending}
                onClick={async () => {
                  if (!active) return;
                  await answer.mutateAsync({ id: active.id, answer: draft.trim() });
                  setActiveId(null);
                }}
              >
                <Send className="size-4" /> Send
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>
    </>
  );
}

// =============================================================================
// InboxCard
// =============================================================================

export function InboxCard() {
  const { data, isLoading } = useInbox(1);
  const { markRead, reply } = useInboxMutations();
  const [openId, setOpenId] = useState<number | null>(null);
  const [body, setBody] = useState("");

  const open = data?.items.find((m) => m.id === openId) ?? null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardKicker>Inbox</CardKicker>
          <CardTitle>Non-blocking notes from agents</CardTitle>
          <CardDescription>
            <code className="font-mono">INBOX:</code> markers — the dispatcher will keep
            running while you read.
          </CardDescription>
        </CardHeader>
        {isLoading ? (
          <CardSkeleton lines={3} />
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-text-dim flex items-center gap-2">
            <Inbox className="size-4 text-text-subtle" />
            Inbox zero.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {data.items.map((m) => (
              <li key={m.id} className="py-3 grid grid-cols-[1fr_auto] items-start gap-3">
                <div className="min-w-0">
                  <div className="text-sm text-text line-clamp-2">{m.body}</div>
                  <div className="text-[11px] text-text-subtle font-mono mt-0.5">
                    task #{m.task_id ?? "—"} · {rel(m.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Badge tone="info">unread</Badge>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setOpenId(m.id);
                      setBody("");
                    }}
                  >
                    Reply
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => markRead.mutate(m.id)}
                  >
                    Mark read
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Sheet
        open={openId !== null}
        onClose={() => setOpenId(null)}
        title="Reply"
        description={open ? `task #${open.task_id ?? "—"}` : ""}
      >
        {open ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-text-dim whitespace-pre-wrap border-l-2 border-info/40 pl-3">
              {open.body}
            </p>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={5}
              autoFocus
              placeholder="Reply — appears in the dispatched session's stdin and is logged here."
              className="w-full rounded-lg bg-surface-2 border border-border p-3 text-sm placeholder:text-text-subtle outline-none focus:border-accent-start"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="md" onClick={() => setOpenId(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="md"
                disabled={!body.trim()}
                loading={reply.isPending}
                onClick={async () => {
                  if (!open) return;
                  await reply.mutateAsync({ id: open.id, body: body.trim() });
                  setOpenId(null);
                }}
              >
                <Send className="size-4" /> Send
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>
    </>
  );
}
