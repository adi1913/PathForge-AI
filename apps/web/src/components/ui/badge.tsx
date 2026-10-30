import * as React from "react";
import { cn, humanize, type Tone } from "@/lib/utils";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  success: "bg-success text-success-foreground",
  warning: "bg-warning text-warning-foreground",
  danger: "bg-destructive text-destructive-foreground",
  info: "bg-primary/15 text-primary",
};

export function Badge({ tone = "neutral", className, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", TONE_CLASS[tone], className)} {...props} />
  );
}

export function StatusBadge({ value, tone }: { value: string | null | undefined; tone: Tone }) {
  return <Badge tone={tone}>{humanize(value)}</Badge>;
}
