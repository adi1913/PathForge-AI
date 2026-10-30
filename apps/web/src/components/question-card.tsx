import type { S } from "@/lib/api";
import { humanize } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";

/** Renders only key-free QuestionOut fields. Coding answers are marked rubric-only: code is never run. */
export function QuestionCard({
  question,
  index,
  value,
  onChange,
}: {
  question: S["QuestionOut"];
  index: number;
  value: string;
  onChange: (v: string) => void;
}) {
  const name = `q-${question.id}`;
  return (
    <Card>
      <CardContent className="space-y-2 p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Question {index + 1}</span>
          <Badge>{humanize(question.question_type)}</Badge>
          {question.difficulty ? <Badge>{humanize(question.difficulty)}</Badge> : null}
        </div>
        <p className="text-sm font-medium">{question.text}</p>
        {question.question_type === "multiple_choice" ? (
          <fieldset className="space-y-1">
            <legend className="sr-only">Choose an answer</legend>
            {(question.options ?? []).map((o) => (
              <label key={o.id} className="flex cursor-pointer items-start gap-2 text-sm">
                <input type="radio" name={name} value={o.id} checked={value === o.id} onChange={() => onChange(o.id)} className="mt-1" />
                <span>
                  <strong>{o.id}.</strong> {o.text}
                </span>
              </label>
            ))}
          </fieldset>
        ) : (
          <>
            <Textarea
              aria-label={`Answer to question ${index + 1}`}
              rows={question.question_type === "coding" ? 8 : 3}
              className={question.question_type === "coding" ? "font-mono text-xs" : undefined}
              value={value}
              onChange={(e) => onChange(e.target.value)}
            />
            {question.question_type === "coding" ? (
              <p className="text-xs text-muted-foreground">Coding answers are checked against a text rubric only. Your code is not run, tested or security-reviewed.</p>
            ) : (
              <p className="text-xs text-muted-foreground">Short answers are scored by a keyword rubric and can miss valid wording.</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
