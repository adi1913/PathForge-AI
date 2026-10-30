"use client";

import { useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText } from "@/lib/use-load";
import { formatConfidence, humanize, toneFor } from "@/lib/utils";
import { ErrorNote, Notice, PageHeader, Stat, UserGate } from "@/components/common";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";

export default function JobsPage() {
  return (
    <>
      <PageHeader
        title="Job analysis"
        description="Compare a job description with your recorded skills. Gaps are rule-based and show the reasoning behind each one."
      />
      <UserGate>{(userId) => <JobForm userId={userId} />}</UserGate>
    </>
  );
}

function GapTable({ title, rows }: { title: string; rows: S["SkillGapResult"][] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {title} ({rows.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {rows.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> : null}
        {rows.length ? (
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3">Skill</th>
                <th className="pr-3">Needed</th>
                <th className="pr-3">You</th>
                <th className="pr-3">Severity</th>
                <th className="pr-3">Priority</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((g) => (
                <tr key={`${g.skill_slug}-${g.requirement_type}`} className="border-t border-border align-top">
                  <td className="py-1.5 pr-3 font-medium">{g.skill_name}</td>
                  <td className="pr-3">{humanize(g.expected_level)}</td>
                  <td className="pr-3">
                    {humanize(g.current_level)} <span className="text-xs text-muted-foreground">({formatConfidence(g.confidence)})</span>
                  </td>
                  <td className="pr-3">
                    <StatusBadge value={g.severity} tone={toneFor(g.severity)} />
                  </td>
                  <td className="pr-3">{g.priority_score.toFixed(0)}</td>
                  <td className="text-xs text-muted-foreground">{g.reasoning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </CardContent>
    </Card>
  );
}

function JobForm({ userId }: { userId: string }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<S["JobDescriptionAnalyzeResponse"] | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() && !file) {
      setError("Paste a job description or choose a file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await api.analyzeJob(userId, { text: text.trim() || undefined, file: file ?? undefined }));
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const jd = result?.job_description;
  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="p-4">
          <form onSubmit={submit} className="space-y-3">
            <div>
              <Label htmlFor="jd-text">Job description</Label>
              <Textarea id="jd-text" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the job description" />
            </div>
            <div>
              <Label htmlFor="jd-file">…or upload a file</Label>
              <Input id="jd-file" type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Analyzing..." : "Analyze job description"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <ErrorNote message={error} />
      {result && jd ? (
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold">{jd.title ?? jd.role ?? "Job description"}</h2>
            <p className="text-sm text-muted-foreground">{jd.company ?? "Company not detected"}</p>
            <CardDescription className="mt-1">Saved as {result.job_description_id}; use it when generating a roadmap or tracking an application.</CardDescription>
          </div>
          {result.warnings.length ? <Notice tone="warning">{result.warnings.join(" · ")}</Notice> : null}
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Match score" value={result.overall_match_score === null ? "n/a" : `${Math.round(result.overall_match_score)}%`} />
            <Stat label="Matched" value={result.user_skill_summary.matched_count} />
            <Stat label="Weak" value={result.user_skill_summary.weak_count} />
            <Stat label="Missing" value={result.user_skill_summary.missing_count} />
          </div>
          <GapTable title="Skill gaps (by priority)" rows={result.skill_gaps} />
          {jd.unmatched_skills.length ? (
            <p className="text-xs text-muted-foreground">Requirements not in the skill catalog: {jd.unmatched_skills.join(", ")}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
