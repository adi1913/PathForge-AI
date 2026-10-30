"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText, useLoad } from "@/lib/use-load";
import { formatDate } from "@/lib/utils";
import { Empty, ErrorNote, Loading, PageHeader, UserGate } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { AnswerSourceLabel, CitationList, MissingContext } from "@/components/mentor-parts";

export default function MentorPage() {
  return (
    <>
      <PageHeader
        title="Mentor"
        description="Ask about your roadmap, progress or a topic. Explanations cite retrieved sources; when none are relevant the mentor says so instead of guessing."
      />
      <UserGate>{(userId) => <Mentor userId={userId} />}</UserGate>
    </>
  );
}

interface Turn {
  id: string;
  role: "user" | "mentor";
  content: string;
  reply?: S["MentorReply"];
}

function Mentor({ userId }: { userId: string }) {
  const sessions = useLoad(() => api.listMentorSessions(userId), userId);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [turns]);

  async function open(id: string) {
    setError(null);
    try {
      const detail = await api.getMentorSession(id, userId);
      setSessionId(id);
      setTurns(detail.messages.map((m) => ({ id: m.id, role: m.role === "user" ? "user" : "mentor", content: m.content })));
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = text.trim();
    if (!message) return;
    setBusy(true);
    setError(null);
    try {
      let id = sessionId;
      if (!id) {
        id = (await api.createMentorSession(userId)).id;
        setSessionId(id);
      }
      const reply = await api.sendMentorMessage(id, userId, message);
      setTurns((t) => [
        ...t,
        { id: reply.user_message_id, role: "user", content: message },
        { id: reply.mentor_message_id, role: "mentor", content: reply.answer, reply },
      ]);
      setText("");
      sessions.reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <Card>
        <CardContent className="space-y-1 p-2">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => {
              setSessionId(null);
              setTurns([]);
            }}
          >
            New conversation
          </Button>
          {sessions.loading ? <Loading /> : null}
          {sessions.data?.map((s) => (
            <button
              key={s.id}
              type="button"
              aria-pressed={sessionId === s.id}
              onClick={() => open(s.id)}
              className="w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted aria-pressed:bg-muted"
            >
              <span className="line-clamp-1">{s.title ?? "Untitled"}</span>
              <span className="block text-xs text-muted-foreground">{formatDate(s.updated_at)}</span>
            </button>
          ))}
        </CardContent>
      </Card>
      <div className="space-y-3">
        <ErrorNote message={error ?? sessions.error} />
        <div className="space-y-3" aria-live="polite">
          {turns.length === 0 ? <Empty>Try: &ldquo;What should I learn next?&rdquo;, &ldquo;Explain RAG&rdquo;, &ldquo;Quiz me on Python&rdquo; or &ldquo;How am I doing?&rdquo;</Empty> : null}
          {turns.map((t) => (
            <div key={t.id} className={t.role === "user" ? "ml-auto max-w-[85%]" : "max-w-[92%]"}>
              <Card className={t.role === "user" ? "bg-muted" : undefined}>
                <CardContent className="p-3 text-sm">
                  <div className="mb-1 text-xs font-medium text-muted-foreground">{t.role === "user" ? "You" : "Mentor"}</div>
                  <div className="whitespace-pre-wrap">{t.content}</div>
                  {t.reply ? (
                    <>
                      <CitationList citations={t.reply.citations} />
                      <MissingContext items={t.reply.missing_context} />
                      {t.reply.actions.map((a) =>
                        a.assessment_id ? (
                          <Link key={a.assessment_id} className="mt-2 inline-block text-xs underline" href={`/assessments?assessment=${a.assessment_id}`}>
                            Open the assessment
                          </Link>
                        ) : null,
                      )}
                      <AnswerSourceLabel source={t.reply.answer_source} />
                    </>
                  ) : null}
                </CardContent>
              </Card>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <form onSubmit={send} className="space-y-2">
          <Textarea aria-label="Message" rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask the mentor (max 2000 characters)" />
          <Button type="submit" disabled={busy || !text.trim()}>
            {busy ? "Thinking..." : "Send"}
          </Button>
        </form>
      </div>
    </div>
  );
}
