import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { S } from "@/lib/api";
import { UserGate } from "@/components/common";
import { clearSession, setSession } from "@/lib/auth";
import { AnswerSourceLabel, CitationList, MissingContext } from "@/components/mentor-parts";
import { QuestionCard } from "@/components/question-card";
import { ReadinessView } from "@/components/readiness";
import { SubmitResult } from "@/components/submit-result";

const mcq: S["QuestionOut"] = {
  id: "q1",
  order_index: 0,
  question_type: "multiple_choice",
  difficulty: "beginner",
  text: "What does RAG stand for?",
  options: [
    { id: "A", text: "Retrieval augmented generation" },
    { id: "B", text: "Random access graph" },
  ],
};

describe("QuestionCard", () => {
  it("lets the learner pick an option and reports it", async () => {
    const onChange = vi.fn();
    render(<QuestionCard question={mcq} index={0} value="" onChange={onChange} />);
    await userEvent.click(screen.getByLabelText(/Retrieval augmented generation/));
    expect(onChange).toHaveBeenCalledWith("A");
  });

  it("labels coding answers as rubric-only and not executed", () => {
    const coding: S["QuestionOut"] = { ...mcq, id: "q2", question_type: "coding", options: null, text: "Write a function" };
    render(<QuestionCard question={coding} index={1} value="" onChange={() => {}} />);
    expect(screen.getByText(/not run, tested or security-reviewed/i)).toBeInTheDocument();
  });
});

const submit: S["SubmitOut"] = {
  attempt_id: "a1",
  assessment_id: "s1",
  skill_slug: "rag",
  score_percent: 90,
  outcome: "strong",
  attempt_number: 1,
  is_retake: false,
  generation_source: "demo_bank",
  evaluation_methods: ["exact_match"],
  answers: [
    {
      question_id: "q1",
      question_type: "coding",
      is_correct: true,
      score_percent: 80,
      feedback: "Met 3 of 4 criteria.",
      evaluation: { method: "rubric", notice: "Code was not executed.", executed: false, criteria_met: 3, criteria_total: 4 },
    },
  ],
  confidence: { applied: true, before: 0.5, after: 0.6, delta: 0.1, note: "Strong result.", level_changed: false },
  adaptation: {
    roadmap_id: "r1",
    actions: [{ action: "reduced_estimate", item_title: "Learn RAG", detail: "Halved." }],
    replanned: true,
    warnings: [],
  },
  notices: ["Demo question bank."],
  evidence_id: "e1",
};

describe("SubmitResult", () => {
  it("shows confidence change, that level is untouched, adaptation and the not-executed notice", () => {
    render(<SubmitResult result={submit} />);
    const conf = screen.getByTestId("confidence");
    expect(within(conf).getByText(/0\.50 → 0\.60 \(\+0\.10\)/)).toBeInTheDocument();
    expect(within(conf).getByText(/skill level was not changed/i)).toBeInTheDocument();
    expect(within(screen.getByTestId("adaptation")).getByText(/Reduced estimate: Learn RAG/)).toBeInTheDocument();
    expect(screen.getByText("Code was not executed.")).toBeInTheDocument();
    expect(screen.getByText(/expected answers are never shown/i)).toBeInTheDocument();
  });

  it("says confidence was not changed for retakes", () => {
    const retake = { ...submit, is_retake: true, confidence: { ...submit.confidence, applied: false, after: 0.5, delta: 0 } };
    render(<SubmitResult result={retake} />);
    expect(screen.getByTestId("confidence")).toHaveTextContent(/not changed/);
    expect(screen.getByText(/retake of an identical question set/)).toBeInTheDocument();
  });
});

describe("mentor parts", () => {
  it("renders citations with source details", () => {
    render(
      <CitationList
        citations={[{ index: 1, title: "RAG intro", source: "kb://rag", heading: "Basics", document_id: "d", chunk_id: "c", score: 0.91 }]}
      />,
    );
    expect(screen.getByRole("list", { name: "Sources" })).toHaveTextContent("[1] RAG intro › Basics (kb://rag) · relevance 0.91");
  });

  it("renders nothing when there are no citations or missing items", () => {
    const { container } = render(
      <>
        <CitationList citations={[]} />
        <MissingContext items={[]} />
      </>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("discloses missing context and the answer source", () => {
    render(
      <>
        <MissingContext items={["No relevant document was found in the knowledge base for this question."]} />
        <AnswerSourceLabel source="demo_rules" />
      </>,
    );
    expect(screen.getByRole("note")).toHaveTextContent(/Missing context:.*No relevant document/);
    expect(screen.getByText(/Answered by rules/)).toBeInTheDocument();
  });
});

describe("ReadinessView", () => {
  const base: S["ReadinessResponse"] = {
    application_id: "a",
    status: "partial",
    reason: "Some skills are weak.",
    overall_match_score: 61.4,
    matched_count: 2,
    weak_count: 1,
    missing_count: 1,
    critical_gap_count: 0,
    high_gap_count: 1,
    skills: [],
    unmatched_requirements: [],
    jd_analyzed_at: null,
    skills_last_updated: null,
    persisted_gaps_may_be_stale: true,
    roadmap: null,
    factors: ["2 matched"],
    warnings: [],
    disclaimer: "Readiness is an estimate, not a prediction of hiring outcomes.",
  };
  it("shows the stale warning, score and disclaimer", () => {
    render(<ReadinessView readiness={base} />);
    expect(screen.getByText(/Readiness: Partial · 61% match/)).toBeInTheDocument();
    expect(screen.getByText(/may be out of date/)).toBeInTheDocument();
    expect(screen.getByText(/not a prediction of hiring outcomes/)).toBeInTheDocument();
  });
});

describe("UserGate", () => {
  it("shows no content when nobody is signed in", async () => {
    clearSession();
    render(<UserGate>{(id) => <div>hello {id}</div>}</UserGate>);
    expect(await screen.findByText(/Redirecting to sign in/)).toBeInTheDocument();
    expect(screen.queryByText(/hello/)).toBeNull();
  });
  it("renders children with the authenticated user's id", async () => {
    setSession({ token: "t", user: { id: "u-42", email: "u@example.com", display_name: null, is_admin: false } });
    render(<UserGate>{(id) => <div>hello {id}</div>}</UserGate>);
    expect(await screen.findByText("hello u-42")).toBeInTheDocument();
    clearSession();
  });
});
