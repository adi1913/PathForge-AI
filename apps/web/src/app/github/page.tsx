"use client";

import { useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText, useLoad } from "@/lib/use-load";
import { formatConfidence, formatDate, humanize } from "@/lib/utils";
import { Empty, ErrorNote, Loading, Notice, PageHeader, UserGate } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

export default function GithubPage() {
  return (
    <>
      <PageHeader
        title="GitHub evidence"
        description="A bounded inspection of a public repository. Observations are evidence of what a repo uses, not proof of proficiency, and never change a skill level."
      />
      <UserGate>{(userId) => <Github userId={userId} />}</UserGate>
    </>
  );
}

function Github({ userId }: { userId: string }) {
  const repos = useLoad(() => api.listRepos(userId), userId);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<S["EvaluationResponse"] | null>(null);

  async function evaluate(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.evaluateRepo(userId, url.trim()));
      repos.reload();
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function show(id: string) {
    setError(null);
    try {
      setResult(await api.getEvaluation(id, userId));
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="p-4">
          <form onSubmit={evaluate} className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <Label htmlFor="gh-url">Repository URL</Label>
              <Input id="gh-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo" />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Inspecting..." : "Evaluate"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <ErrorNote message={error ?? repos.error} />
      {result ? <Evaluation result={result} /> : null}
      <Card>
        <CardHeader>
          <CardTitle>Evaluated repositories</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {repos.loading ? <Loading /> : null}
          {repos.data?.length === 0 ? <Empty>No repositories evaluated yet.</Empty> : null}
          {repos.data?.map((r) => (
            <div key={r.id} className="flex items-center justify-between text-sm">
              <span>
                {r.github_url}
                <span className="block text-xs text-muted-foreground">Last analyzed {formatDate(r.last_analyzed_at)}</span>
              </span>
              {r.latest_evaluation_id ? (
                <Button size="sm" variant="outline" onClick={() => show(r.latest_evaluation_id as string)}>
                  View
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function Evaluation({ result }: { result: S["EvaluationResponse"] }) {
  const r = result.repository;
  return (
    <div className="space-y-3">
      <Notice tone={result.data_source === "demo" ? "warning" : "info"}>
        Data source: <strong>{humanize(result.data_source)}</strong>
        {result.data_source === "demo" ? " (fixture data, not read from GitHub)" : ""}. {result.note}
      </Notice>
      <Card>
        <CardHeader>
          <CardTitle>{r.full_name}</CardTitle>
          <CardDescription>
            {r.description ?? "No description"} · {r.stars} stars {r.is_fork ? "· fork" : ""} {r.is_archived ? "· archived" : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(result.languages_percent).map(([lang, pct]) => (
              <Badge key={lang}>
                {lang} {Number(pct).toFixed(0)}%
              </Badge>
            ))}
          </div>
          {result.evidence.map((g) => (
            <div key={g.skill_id} className="rounded-md border border-border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{g.skill_name}</span>
                <span className="text-xs text-muted-foreground">confidence {formatConfidence(g.aggregate_confidence)}</span>
              </div>
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {g.items.map((i) => (
                  <li key={`${i.evidence_type}-${i.excerpt}`}>
                    {humanize(i.evidence_type)}: {i.excerpt} <em>({i.limitations})</em>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {result.evidence.length === 0 ? <p className="text-sm text-muted-foreground">No catalog skills matched.</p> : null}
          {result.limitations.length ? (
            <ul className="list-disc pl-5 text-xs text-muted-foreground">
              {result.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
