"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { formatPercent, humanize, toneFor } from "@/lib/utils";
import { ErrorNote, Loading, PageHeader, Stat, UserGate, Empty } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export default function OverviewPage() {
  return (
    <>
      <PageHeader title="Overview" description="Where you are against your target role, assembled from the existing API." />
      <UserGate>{(userId) => <Overview userId={userId} />}</UserGate>
    </>
  );
}

function Overview({ userId }: { userId: string }) {
  const roadmaps = useLoad(() => api.listRoadmaps(userId), userId);
  const activeId = roadmaps.data?.find((r) => r.status === "active")?.id ?? roadmaps.data?.[0]?.id ?? null;
  const progress = useLoad(() => api.roadmapProgress(activeId as string, userId), activeId ? `${userId}:${activeId}` : null);
  const apps = useLoad(() => api.listApplications(userId), userId);
  const evidence = useLoad(() => api.assessmentEvidence(userId), userId);
  const repos = useLoad(() => api.listRepos(userId), userId);

  const firstError = roadmaps.error ?? apps.error ?? evidence.error ?? repos.error;
  const byStatus = new Map<string, number>();
  for (const a of apps.data?.items ?? []) byStatus.set(a.status, (byStatus.get(a.status) ?? 0) + 1);
  const latest = evidence.data?.slice(0, 5) ?? [];

  return (
    <div className="space-y-5">
      <ErrorNote message={firstError} onRetry={() => [roadmaps, apps, evidence, repos].forEach((l) => l.reload())} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Roadmaps" value={roadmaps.data?.length ?? "-"} />
        <Stat label="Applications" value={apps.data?.total ?? "-"} />
        <Stat label="Assessment results" value={evidence.data?.length ?? "-"} hint="Stored as separate evidence" />
        <Stat label="Repositories evaluated" value={repos.data?.length ?? "-"} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Roadmap progress</CardTitle>
          <CardDescription>
            Percent by effort across skill items. <Link className="underline" href="/roadmap">Open roadmap</Link>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {roadmaps.loading || progress.loading ? <Loading /> : null}
          {!roadmaps.loading && !activeId ? (
            <Empty>No roadmap yet. Analyze a job description, then generate a roadmap.</Empty>
          ) : null}
          {progress.data ? (
            <div className="space-y-2">
              <Progress value={progress.data.summary.percent_by_effort} label="Roadmap progress by effort" />
              <p className="text-sm">
                {formatPercent(progress.data.summary.percent_by_effort)} by effort · {progress.data.summary.completed} of{" "}
                {progress.data.summary.total_skills} skills completed · {progress.data.summary.in_progress} in progress ·{" "}
                re-plans so far: {progress.data.replan_count}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Applications by status</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {byStatus.size === 0 ? <span className="text-sm text-muted-foreground">No applications tracked.</span> : null}
            {[...byStatus.entries()].map(([status, n]) => (
              <Badge key={status} tone={toneFor(status)}>
                {humanize(status)}: {n}
              </Badge>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recent assessment evidence</CardTitle>
            <CardDescription>Confidence only: assessments never change a skill&apos;s level.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {latest.length === 0 ? <span className="text-sm text-muted-foreground">No assessments submitted yet.</span> : null}
            {latest.map((e) => (
              <div key={e.id} className="flex items-center justify-between text-sm">
                <span>{e.skill_name}</span>
                <span className="flex items-center gap-2">
                  {formatPercent(e.score_percent)}
                  <Badge tone={toneFor(e.outcome)}>{humanize(e.outcome)}</Badge>
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
