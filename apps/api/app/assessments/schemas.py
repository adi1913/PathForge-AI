"""User-facing assessment schemas. NOTE: no schema here has a field for the answer key (expected option,
rubric criteria or keyword patterns) — a regression test walks the OpenAPI document to keep it that way."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import AssessmentOutcome, AssessmentType, Difficulty, QuestionType

SOURCE_LABELS = {
    "demo_bank": "Demo question bank: fixed fixture questions, not live or AI-generated content.",
    "llm": "Questions drafted by the configured LLM provider; grading is still deterministic.",
}
GRADING_NOTICE = (
    "Multiple choice is graded by exact match. Short answers and coding answers are graded against a keyword/"
    "text rubric, not a semantic judgement. Submitted code is never executed, so no tests, correctness, "
    "security or code-quality analysis is performed."
)


class OptionOut(BaseModel):
    id: str
    text: str


class QuestionOut(BaseModel):
    id: str
    order_index: int
    question_type: QuestionType
    difficulty: Difficulty | None
    text: str
    options: list[OptionOut] | None = None


class AssessmentOut(BaseModel):
    id: str
    user_id: str
    skill_slug: str | None
    skill_name: str | None
    roadmap_item_id: str | None
    title: str
    assessment_type: AssessmentType
    generation_source: str
    source_label: str
    grading_notice: str = GRADING_NOTICE
    questions: list[QuestionOut]
    created_at: datetime


class AssessmentListItem(BaseModel):
    id: str
    title: str
    skill_slug: str | None
    assessment_type: AssessmentType
    generation_source: str
    question_count: int
    attempts: int
    created_at: datetime


class GenerateRequest(BaseModel):
    user_id: str
    skill_slug: str | None = Field(default=None, max_length=150)
    roadmap_item_id: str | None = None
    assessment_type: AssessmentType = AssessmentType.QUIZ
    question_count: int = Field(default=5, ge=3, le=10)


class AttemptStartRequest(BaseModel):
    user_id: str


class AttemptStartOut(BaseModel):
    attempt_id: str
    assessment_id: str
    started_at: datetime
    resumed: bool  # an open attempt already existed and is returned instead of creating another
    questions: list[QuestionOut]


class AnswerIn(BaseModel):
    question_id: str
    answer: str = Field(max_length=10_000)  # tightened per question type in the service


class SubmitRequest(BaseModel):
    user_id: str
    answers: list[AnswerIn] = Field(max_length=10)


class AnswerEvaluation(BaseModel):
    method: str
    notice: str | None = None
    executed: bool | None = None  # present (false) for coding answers: code is never run
    criteria_met: int | None = None
    criteria_total: int | None = None


class AnswerResult(BaseModel):
    question_id: str
    question_type: QuestionType
    is_correct: bool
    score_percent: float
    feedback: str
    evaluation: AnswerEvaluation


class ConfidenceOut(BaseModel):
    applied: bool
    before: float | None
    after: float | None
    delta: float
    note: str
    level_changed: Literal[False] = False  # skill level and source are never changed by assessments


class AdaptationAction(BaseModel):
    action: str
    item_title: str
    detail: str


class AdaptationOut(BaseModel):
    roadmap_id: str | None
    actions: list[AdaptationAction]
    replanned: bool
    warnings: list[str]


class SubmitOut(BaseModel):
    attempt_id: str
    assessment_id: str
    skill_slug: str | None
    score_percent: float
    outcome: AssessmentOutcome
    attempt_number: int
    is_retake: bool
    generation_source: str
    evaluation_methods: list[str]
    answers: list[AnswerResult]
    confidence: ConfidenceOut
    adaptation: AdaptationOut
    notices: list[str]
    evidence_id: str


class EvidenceOut(BaseModel):
    id: str
    skill_slug: str
    skill_name: str
    assessment_id: str | None
    attempt_id: str | None
    attempt_number: int
    score_percent: float
    outcome: AssessmentOutcome
    assessment_type: str
    question_count: int
    evaluation_methods: list[str]
    confidence_before: float | None
    confidence_after: float | None
    confidence_delta_applied: float
    confidence_note: str
    rules_version: str
    data_source: str
    created_at: datetime
