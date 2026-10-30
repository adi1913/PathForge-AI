"use client";

import { useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText } from "@/lib/use-load";
import { formatConfidence, humanize } from "@/lib/utils";
import { ErrorNote, Notice, PageHeader, UserGate } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";

export default function ResumePage() {
  return (
    <>
      <PageHeader
        title="Resume"
        description="Extract skills with evidence from a resume. Levels are inferred from the text, not verified; assessments and repositories add separate evidence."
      />
      <UserGate>{(userId) => <ResumeForm userId={userId} />}</UserGate>
    </>
  );
}

function ResumeForm({ userId }: { userId: string }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<S["ResumeAnalyzeResponse"] | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() && !file) {
      setError("Paste resume text or choose a file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await api.analyzeResume(userId, { text: text.trim() || undefined, file: file ?? undefined }));
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const analysis = result?.analysis;
  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="p-4">
          <form onSubmit={submit} className="space-y-3">
            <div>
              <Label htmlFor="resume-text">Resume text</Label>
              <Textarea id="resume-text" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste your resume here" />
            </div>
            <div>
              <Label htmlFor="resume-file">…or upload a file (PDF, DOCX, TXT)</Label>
              <Input id="resume-file" type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Analyzing..." : "Analyze resume"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <ErrorNote message={error} />
      {result && analysis ? (
        <div className="space-y-4">
          <Notice>
            Saved {result.user_skills_created} new and {result.user_skills_updated} updated skills. Existing assessment evidence is preserved on
            re-analysis.
          </Notice>
          {analysis.warnings.length ? <Notice tone="warning">{analysis.warnings.join(" · ")}</Notice> : null}
          <Card>
            <CardHeader>
              <CardTitle>Skills ({analysis.skills.length})</CardTitle>
              <CardDescription>Each skill shows where the evidence came from.</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3">Skill</th>
                    <th className="pr-3">Inferred level</th>
                    <th className="pr-3">Confidence</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.skills.map((s) => (
                    <tr key={s.skill_name} className="border-t border-border align-top">
                      <td className="py-1.5 pr-3 font-medium">{s.normalized_skill ?? s.skill_name}</td>
                      <td className="pr-3">
                        <Badge>{humanize(s.inferred_level)}</Badge>
                      </td>
                      <td className="pr-3">{formatConfidence(s.confidence)}</td>
                      <td className="text-xs text-muted-foreground">
                        {humanize(s.evidence_type)} · {s.source_section}: {s.evidence_text}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {analysis.unmatched_skills.length ? (
                <p className="mt-3 text-xs text-muted-foreground">Not in the skill catalog: {analysis.unmatched_skills.join(", ")}</p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
