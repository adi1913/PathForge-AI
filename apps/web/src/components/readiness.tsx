import type { S } from "@/lib/api";
import { formatConfidence, humanize, toneFor } from "@/lib/utils";
import { Notice } from "@/components/common";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Read-only readiness: shows reasons, factors, stale warnings and the disclaimer instead of a bare score. */
export function ReadinessView({ readiness }: { readiness: S["ReadinessResponse"] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Readiness: {humanize(readiness.status)}
          {readiness.overall_match_score !== null ? ` · ${Math.round(readiness.overall_match_score)}% match` : ""}
        </CardTitle>
        {readiness.reason ? <CardDescription>{readiness.reason}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge tone="success">Matched {readiness.matched_count}</Badge>
          <Badge tone="warning">Weak {readiness.weak_count}</Badge>
          <Badge tone="danger">Missing {readiness.missing_count}</Badge>
        </div>
        {readiness.persisted_gaps_may_be_stale ? (
          <Notice tone="warning">Stored skill gaps may be out of date: your skills changed after the job description was analyzed.</Notice>
        ) : null}
        {readiness.warnings.length ? <Notice tone="warning">{readiness.warnings.join(" · ")}</Notice> : null}
        <ul className="space-y-1.5 text-sm">
          {readiness.skills.map((s) => (
            <li key={`${s.skill_name}-${s.requirement_type}`} className="rounded-md border border-border p-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{s.skill_name}</span>
                <span className="flex items-center gap-2">
                  <StatusBadge value={s.match_status} tone={toneFor(s.match_status)} />
                  <span className="text-xs text-muted-foreground">
                    {humanize(s.current_level)} of {humanize(s.expected_level)} · confidence {formatConfidence(s.confidence)}
                  </span>
                </span>
              </div>
              <div className="text-xs text-muted-foreground">{s.reasoning}</div>
              {s.github_evidence.length ? (
                <div className="mt-1 text-xs text-muted-foreground">
                  Repository evidence (does not change level): {s.github_evidence.map((g) => `${g.repository} (${humanize(g.evidence_type)})`).join(", ")}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        {readiness.factors.length ? (
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {readiness.factors.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        ) : null}
        <p className="text-xs text-muted-foreground">{readiness.disclaimer}</p>
      </CardContent>
    </Card>
  );
}
