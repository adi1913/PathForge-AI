"use client";

import { useEffect, useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText, useLoad } from "@/lib/use-load";
import { formatDate, formatMinutes, formatPercent, humanize, toneFor } from "@/lib/utils";
import { Empty, ErrorNote, Loading, Notice, PageHeader, Stat, UserGate } from "@/components/common";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

const STATUSES: S["RoadmapItemStatus"][] = ["not_started", "in_progress", "completed", "skipped", "blocked"];

export default function RoadmapPage() {
  return (
    <>
      <PageHeader
        title="Roadmap"
        description="An adaptive plan built from your skill gaps. Marking progress and re-planning reorder what is left; assessments can also adapt it."
      />
      <UserGate>{(userId) => <Roadmaps userId={userId} />}</UserGate>
    </>
  );
}

function Roadmaps({ userId }: { userId: string }) {
  const list = useLoad(() => api.listRoadmaps(userId), userId);
  const [selected, setSelected] = useState<string>("");
  const [hours, setHours] = useState("2");
  const [days, setDays] = useState("");
  const [jdId, setJdId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (list.data && !list.data.some((r) => r.id === selected)) {
      setSelected(list.data.find((r) => r.status === "active")?.id ?? list.data[0]?.id ?? "");
    }
  }, [list.data, selected]);

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.generateRoadmap({
        user_id: userId,
        hours_per_day: hours ? Number(hours) : null,
        duration_days: days ? Number(days) : null,
        job_description_id: jdId.trim() || null,
      });
      setSelected(created.id);
      list.reload();
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
          <CardTitle>Generate a roadmap</CardTitle>
          <CardDescription>Uses your latest skill gaps. Optionally pin a job description id from the Job analysis page.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={generate} className="flex flex-wrap items-end gap-3">
            <div>
              <Label htmlFor="rm-hours">Hours per day</Label>
              <Input id="rm-hours" className="w-28" type="number" min="0.5" max="12" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="rm-days">Deadline (days, optional)</Label>
              <Input id="rm-days" className="w-36" type="number" min="1" value={days} onChange={(e) => setDays(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="rm-jd">Job description id (optional)</Label>
              <Input id="rm-jd" className="w-72" value={jdId} onChange={(e) => setJdId(e.target.value)} />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Generating..." : "Generate"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <ErrorNote message={error ?? list.error} onRetry={list.reload} />
      {list.loading ? <Loading /> : null}
      {list.data && list.data.length === 0 ? <Empty>No roadmaps yet. Generate one after analyzing a job description.</Empty> : null}
      {list.data && list.data.length > 0 ? (
        <div className="space-y-4">
          <div className="max-w-md">
            <Label htmlFor="rm-select">Roadmap</Label>
            <Select id="rm-select" value={selected} onChange={(e) => setSelected(e.target.value)}>
              {list.data.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title} ({humanize(r.status)}, {formatDate(r.created_at)})
                </option>
              ))}
            </Select>
          </div>
          {selected ? <RoadmapDetail key={selected} userId={userId} roadmapId={selected} onChanged={list.reload} /> : null}
        </div>
      ) : null}
    </div>
  );
}

function RoadmapDetail({ userId, roadmapId, onChanged }: { userId: string; roadmapId: string; onChanged: () => void }) {
  const roadmap = useLoad(() => api.getRoadmap(roadmapId), roadmapId);
  const progress = useLoad(() => api.roadmapProgress(roadmapId, userId), `${roadmapId}:${userId}`);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    roadmap.reload();
    progress.reload();
    onChanged();
  };

  async function setStatus(item: S["RoadmapItemOut"], status: S["RoadmapItemStatus"]) {
    setError(null);
    setBusy(true);
    try {
      const res = await api.updateProgress(roadmapId, item.id, { user_id: userId, status });
      setNotice(res.warnings);
      refresh();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function replan() {
    setError(null);
    setBusy(true);
    try {
      const res = await api.replan(roadmapId, { user_id: userId });
      setNotice([
        `Re-planned: ${res.replan.remaining_skills} skills left (${formatMinutes(res.replan.remaining_minutes)}), ~${res.replan.estimated_weeks} weeks, ${res.replan.changed_items} items changed.` +
          (res.replan.fits_deadline === false ? " It does not fit the deadline." : ""),
        ...(res.replan.stalled_skills.length ? [`Stalled: ${res.replan.stalled_skills.join(", ")}`] : []),
      ]);
      refresh();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const summary = progress.data?.summary;
  return (
    <div className="space-y-4">
      <ErrorNote message={error ?? roadmap.error ?? progress.error} onRetry={refresh} />
      {notice.length ? <Notice>{notice.join(" ")}</Notice> : null}
      {roadmap.data?.warnings.length ? <Notice tone="warning">{roadmap.data.warnings.join(" · ")}</Notice> : null}
      {summary ? (
        <div className="grid gap-3 sm:grid-cols-4">
          <Stat label="By effort" value={formatPercent(summary.percent_by_effort)} />
          <Stat label="By items" value={formatPercent(summary.percent_by_items)} />
          <Stat label="Completed" value={`${summary.completed}/${summary.total_skills}`} hint="skill items" />
          <Stat label="Re-plans" value={progress.data?.replan_count ?? 0} />
        </div>
      ) : null}
      {summary ? <Progress value={summary.percent_by_effort} label="Roadmap progress by effort" /> : null}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{roadmap.data?.title}</h2>
        <Button variant="outline" size="sm" onClick={replan} disabled={busy}>
          Re-plan remaining work
        </Button>
      </div>
      {roadmap.loading ? <Loading /> : null}
      {roadmap.data ? (
        <Card>
          <CardContent className="overflow-x-auto p-2">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th className="px-2 py-1">#</th>
                  <th>Item</th>
                  <th>Type</th>
                  <th>Week</th>
                  <th>Effort</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {[...roadmap.data.items]
                  .sort((a, b) => a.order_index - b.order_index)
                  .map((item) => (
                    <tr key={item.id} className="border-t border-border align-top">
                      <td className="px-2 py-1.5 text-muted-foreground">{item.order_index + 1}</td>
                      <td className="py-1.5 pr-3">
                        <div className="font-medium">{item.title}</div>
                        {item.description ? <div className="text-xs text-muted-foreground">{item.description}</div> : null}
                      </td>
                      <td className="pr-3">{humanize(item.item_type)}</td>
                      <td className="pr-3">{item.week_number ?? "-"}</td>
                      <td className="pr-3">{formatMinutes(item.estimated_minutes)}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <StatusBadge value={item.status} tone={toneFor(item.status)} />
                          <Select
                            aria-label={`Status for ${item.title}`}
                            className="h-8 w-36 text-xs"
                            value={item.status}
                            disabled={busy}
                            onChange={(e) => setStatus(item, e.target.value as S["RoadmapItemStatus"])}
                          >
                            {STATUSES.map((s) => (
                              <option key={s} value={s}>
                                {humanize(s)}
                              </option>
                            ))}
                          </Select>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
      {progress.data?.recent_events.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-muted-foreground">
            {progress.data.recent_events.slice(0, 8).map((e) => (
              <div key={e.id}>
                {formatDate(e.created_at)} · {humanize(e.event_type)}
                {e.previous_value || e.new_value ? `: ${e.previous_value ?? "-"} → ${e.new_value ?? "-"}` : ""}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
