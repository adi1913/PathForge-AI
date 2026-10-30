"use client";

import { useEffect, useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText, useLoad } from "@/lib/use-load";
import { formatConfidence, formatDate, formatPercent, formatSignedDelta, humanize, toneFor } from "@/lib/utils";
import { Empty, ErrorNote, Loading, Notice, PageHeader, UserGate } from "@/components/common";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { QuestionCard } from "@/components/question-card";
import { SubmitResult } from "@/components/submit-result";

const DEMO_SKILLS = ["python", "machine-learning", "llm-genai", "rag", "ai-agents", "mcp", "docker", "fastapi"];

export default function AssessmentsPage() {
  return (
    <>
      <PageHeader
        title="Assessments"
        description="Quizzes and rubric-checked exercises. Results are stored as separate evidence and only adjust confidence by fixed rules; code is never executed."
      />
      <UserGate>{(userId) => <Assessments userId={userId} />}</UserGate>
    </>
  );
}

function Assessments({ userId }: { userId: string }) {
  const list = useLoad(() => api.listAssessments(userId), userId);
  const evidence = useLoad(() => api.assessmentEvidence(userId), userId);
  const [skill, setSkill] = useState("python");
  const [kind, setKind] = useState<S["AssessmentType"]>("quiz");
  const [count, setCount] = useState("5");
  const [active, setActive] = useState<{ attemptId: string; assessment: S["AssessmentOut"] } | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<S["SubmitOut"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function begin(assessmentId: string) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const assessment = await api.getAssessment(assessmentId, userId);
      const attempt = await api.startAttempt(assessmentId, userId);
      setActive({ attemptId: attempt.attempt_id, assessment: { ...assessment, questions: attempt.questions } });
      setAnswers({});
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  // Deep link from the mentor: /assessments?assessment=<id>
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("assessment");
    if (id) void begin(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.generateAssessment({ user_id: userId, skill_slug: skill.trim(), assessment_type: kind, question_count: Number(count) });
      list.reload();
      await begin(created.id);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  async function submit() {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const payload = active.assessment.questions
        .filter((q) => (answers[q.id] ?? "").trim() !== "")
        .map((q) => ({ question_id: q.id, answer: answers[q.id] }));
      const res = await api.submitAttempt(active.attemptId, { user_id: userId, answers: payload });
      setResult(res);
      setActive(null);
      list.reload();
      evidence.reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>New assessment</CardTitle>
          <CardDescription>Without LLM credentials, questions come from a small built-in demo bank and are labelled as such.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={generate} className="flex flex-wrap items-end gap-3">
            <div>
              <Label htmlFor="as-skill">Skill slug</Label>
              <Input id="as-skill" list="demo-skills" className="w-48" value={skill} onChange={(e) => setSkill(e.target.value)} />
              <datalist id="demo-skills">
                {DEMO_SKILLS.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </div>
            <div>
              <Label htmlFor="as-kind">Type</Label>
              <Select id="as-kind" className="w-32" value={kind} onChange={(e) => setKind(e.target.value as S["AssessmentType"])}>
                <option value="quiz">Quiz</option>
                <option value="coding">Coding</option>
                <option value="mixed">Mixed</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="as-count">Questions (3-10)</Label>
              <Input id="as-count" className="w-24" type="number" min="3" max="10" value={count} onChange={(e) => setCount(e.target.value)} />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Working..." : "Generate and start"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <ErrorNote message={error ?? list.error ?? evidence.error} />

      {active ? (
        <div className="space-y-3">
          <div>
            <h2 className="text-base font-semibold">{active.assessment.title}</h2>
            <Notice className="mt-2">
              {active.assessment.source_label} {active.assessment.grading_notice}
            </Notice>
          </div>
          {active.assessment.questions.map((q, i) => (
            <QuestionCard key={q.id} question={q} index={i} value={answers[q.id] ?? ""} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
          ))}
          <Button onClick={submit} disabled={busy}>
            Submit answers
          </Button>
          <p className="text-xs text-muted-foreground">Unanswered questions score zero.</p>
        </div>
      ) : null}

      {result ? <SubmitResult result={result} /> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Your assessments</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {list.loading ? <Loading /> : null}
            {list.data?.length === 0 ? <Empty>None yet.</Empty> : null}
            {list.data?.map((a) => (
              <div key={a.id} className="flex items-center justify-between gap-2 text-sm">
                <span>
                  {a.title}
                  <span className="block text-xs text-muted-foreground">
                    {humanize(a.assessment_type)} · {a.question_count} questions · {a.attempts} attempts · {humanize(a.generation_source)}
                  </span>
                </span>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => begin(a.id)}>
                  Take
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Evidence history</CardTitle>
            <CardDescription>Append-only record. Resume re-analysis never removes it.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {evidence.data?.length === 0 ? <Empty>No results yet.</Empty> : null}
            {evidence.data?.map((e) => (
              <div key={e.id} className="rounded-md border border-border p-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{e.skill_name}</span>
                  <span className="flex items-center gap-2">
                    {formatPercent(e.score_percent)} <StatusBadge value={e.outcome} tone={toneFor(e.outcome)} />
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {formatDate(e.created_at)} · confidence {formatConfidence(e.confidence_before)} → {formatConfidence(e.confidence_after)} (
                  {formatSignedDelta(e.confidence_delta_applied)}) · {e.confidence_note}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
