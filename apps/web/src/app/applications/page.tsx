"use client";

import { useState } from "react";
import { api, type S } from "@/lib/api";
import { errorText, useLoad } from "@/lib/use-load";
import { formatDate, humanize, toneFor } from "@/lib/utils";
import { Empty, ErrorNote, Loading, Notice, PageHeader, UserGate } from "@/components/common";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { ReadinessView } from "@/components/readiness";

const STATUSES: S["ApplicationStatus"][] = ["interested", "preparing", "applied", "assessment", "interview", "offer", "rejected", "withdrawn"];

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Track applications and see read-only readiness computed from your current skill evidence."
      />
      <UserGate>{(userId) => <Applications userId={userId} />}</UserGate>
    </>
  );
}

function Applications({ userId }: { userId: string }) {
  const list = useLoad(() => api.listApplications(userId), userId);
  const [selected, setSelected] = useState<string | null>(null);
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [jdId, setJdId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() && !jdId.trim()) {
      setError("Enter a job title or a job description id.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createApplication({
        user_id: userId,
        company: company.trim() || null,
        job_title: title.trim() || null,
        job_description_id: jdId.trim() || null,
      });
      setCompany("");
      setTitle("");
      setJdId("");
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
          <CardTitle>Track an application</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div>
              <Label htmlFor="app-company">Company</Label>
              <Input id="app-company" className="w-48" value={company} onChange={(e) => setCompany(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="app-title">Job title</Label>
              <Input id="app-title" className="w-56" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="app-jd">Job description id (for readiness)</Label>
              <Input id="app-jd" className="w-72" value={jdId} onChange={(e) => setJdId(e.target.value)} />
            </div>
            <Button type="submit" disabled={busy}>
              Add
            </Button>
          </form>
        </CardContent>
      </Card>
      <ErrorNote message={error ?? list.error} onRetry={list.reload} />
      {list.loading ? <Loading /> : null}
      {list.data && list.data.items.length === 0 ? <Empty>No applications yet.</Empty> : null}
      {list.data && list.data.items.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <Card>
            <CardContent className="p-2">
              <ul>
                {list.data.items.map((a) => (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(a.id)}
                      aria-pressed={selected === a.id}
                      className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-sm hover:bg-muted aria-pressed:bg-muted"
                    >
                      <span>
                        <span className="font-medium">{a.job_title}</span>
                        <span className="block text-xs text-muted-foreground">
                          {a.company ?? "Unknown company"} · updated {formatDate(a.updated_at)}
                        </span>
                      </span>
                      <StatusBadge value={a.status} tone={toneFor(a.status)} />
                    </button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          {selected ? <ApplicationDetail key={selected} userId={userId} id={selected} onChanged={list.reload} /> : <Empty>Select an application.</Empty>}
        </div>
      ) : null}
    </div>
  );
}

function ApplicationDetail({ userId, id, onChanged }: { userId: string; id: string; onChanged: () => void }) {
  const detail = useLoad(() => api.getApplication(id, userId), `${id}:${userId}`);
  const readiness = useLoad(() => api.applicationReadiness(id, userId), `${id}:${userId}`);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function changeStatus(status: S["ApplicationStatus"]) {
    setError(null);
    try {
      await api.updateApplicationStatus(id, { user_id: userId, status });
      detail.reload();
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function addNote(e: React.FormEvent) {
    e.preventDefault();
    if (!note.trim()) return;
    setError(null);
    try {
      await api.addApplicationNote(id, { user_id: userId, note: note.trim() });
      setNote("");
      detail.reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  const d = detail.data;
  return (
    <div className="space-y-3">
      <ErrorNote message={error ?? detail.error} />
      {detail.loading && !d ? <Loading /> : null}
      {d ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {d.job_title} {d.company ? `· ${d.company}` : ""}
            </CardTitle>
            <CardDescription>Invalid status jumps are rejected by the API and shown here.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <Label htmlFor="app-status">Status</Label>
              <Select id="app-status" className="w-44" value={d.status} onChange={(e) => changeStatus(e.target.value as S["ApplicationStatus"])}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {humanize(s)}
                  </option>
                ))}
              </Select>
            </div>
            <form onSubmit={addNote} className="space-y-2">
              <Label htmlFor="app-note">Add a note</Label>
              <Textarea id="app-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              <Button size="sm" type="submit" variant="outline">
                Save note
              </Button>
            </form>
            <div className="space-y-1 text-xs text-muted-foreground">
              {d.events.map((ev) => (
                <div key={ev.id}>
                  {formatDate(ev.occurred_at)} · {humanize(ev.event_type)}
                  {ev.to_status ? ` → ${humanize(ev.to_status)}` : ""}
                  {ev.note ? `: ${ev.note}` : ""}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}
      {readiness.error ? <Notice tone="warning">Readiness unavailable: {readiness.error}</Notice> : null}
      {readiness.data ? <ReadinessView readiness={readiness.data} /> : null}
    </div>
  );
}
