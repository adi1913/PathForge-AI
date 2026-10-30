import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** "in_progress" -> "In progress" */
export function humanize(value: string | null | undefined): string {
  if (!value) return "";
  const text = value.replace(/[_-]+/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(digits)}%`;
}

/** Confidence values are 0..1 in the API. */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(2);
}

export function formatSignedDelta(value: number): string {
  if (value === 0) return "0.00";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatMinutes(minutes: number | null | undefined): string {
  if (!minutes) return "-";
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const TONES: Record<string, Tone> = {
  completed: "success", strong: "success", matched: "success", passed: "success", offer: "success", ready: "success",
  in_progress: "info", applied: "info", interview: "info", screening: "info",
  weak: "warning", blocked: "warning", partial: "warning", insufficient: "warning", skipped: "neutral",
  missing: "danger", rejected: "danger", critical: "danger", high: "warning",
};

export function toneFor(value: string | null | undefined): Tone {
  return TONES[(value ?? "").toLowerCase()] ?? "neutral";
}
