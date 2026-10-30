import type { S } from "@/lib/api";
import { Notice } from "@/components/common";

export function CitationList({ citations }: { citations: S["Citation"][] }) {
  if (citations.length === 0) return null;
  return (
    <ol aria-label="Sources" className="mt-2 space-y-1 text-xs text-muted-foreground">
      {citations.map((c) => (
        <li key={c.chunk_id}>
          [{c.index}] {c.title ?? "Untitled"}
          {c.heading ? ` › ${c.heading}` : ""}
          {c.source ? ` (${c.source})` : ""} · relevance {c.score.toFixed(2)}
        </li>
      ))}
    </ol>
  );
}

export function MissingContext({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Notice tone="warning" className="mt-2">
      <strong>Missing context:</strong> {items.join(" ")}
    </Notice>
  );
}

export function AnswerSourceLabel({ source }: { source: string }) {
  const text = source === "llm" ? "Answered by the configured LLM, using only retrieved sources" : "Answered by rules (demo or LLM unavailable), not an LLM";
  return <div className="mt-1 text-[11px] text-muted-foreground">{text}</div>;
}
