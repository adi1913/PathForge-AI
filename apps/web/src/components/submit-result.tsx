import type { S } from "@/lib/api";
import { formatConfidence, formatPercent, formatSignedDelta, humanize, toneFor } from "@/lib/utils";
import { Notice } from "@/components/common";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function SubmitResult({ result }: { result: S["SubmitOut"] }) {
  const c = result.confidence;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>
            Score {formatPercent(result.score_percent)} · <StatusBadge value={result.outcome} tone={toneFor(result.outcome)} />
          </CardTitle>
          <CardDescription>
            Attempt {result.attempt_number}
            {result.is_retake ? " (retake of an identical question set)" : ""} · source: {humanize(result.generation_source)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div data-testid="confidence" className="rounded-md border border-border p-3 text-sm">
            <div className="font-medium">
              Confidence {c.applied ? "updated" : "not changed"}: {formatConfidence(c.before)} → {formatConfidence(c.after)} ({formatSignedDelta(c.delta)})
            </div>
            <div className="text-xs text-muted-foreground">{c.note}</div>
            <div className="text-xs text-muted-foreground">Your skill level was not changed. Assessments only adjust confidence.</div>
          </div>
          {result.adaptation.actions.length || result.adaptation.warnings.length ? (
            <div data-testid="adaptation" className="space-y-1 text-sm">
              <div className="font-medium">Roadmap adaptation{result.adaptation.replanned ? " (re-planned)" : ""}</div>
              <ul className="list-disc pl-5 text-xs text-muted-foreground">
                {result.adaptation.actions.map((a) => (
                  <li key={`${a.action}-${a.item_title}`}>
                    {humanize(a.action)}: {a.item_title}. {a.detail}
                  </li>
                ))}
                {result.adaptation.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.notices.map((n) => (
            <Notice key={n}>{n}</Notice>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Per-question feedback</CardTitle>
          <CardDescription>Feedback shows counts only; expected answers are never shown.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {result.answers.map((a, i) => (
            <div key={a.question_id} className="rounded-md border border-border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span>
                  Question {i + 1} · {humanize(a.question_type)}
                </span>
                <Badge tone={a.is_correct ? "success" : "warning"}>{formatPercent(a.score_percent)}</Badge>
              </div>
              <div className="text-xs text-muted-foreground">{a.feedback}</div>
              {a.evaluation.executed === false ? (
                <div className="text-xs text-muted-foreground">{a.evaluation.notice ?? "Code was not executed."}</div>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
