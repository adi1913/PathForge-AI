"""Question sources. DEMO_MODE draws fixed fixture questions from bank.py; real mode asks the configured
LLMProvider to draft questions (validated by Pydantic). Either way the result is a list of QuestionSpec —
grading is always the deterministic code in grading.py, never an LLM."""

from typing import Protocol

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agent.errors import AgentError
from app.agent.llm.base import LLMProvider
from app.assessments.bank import BANK, QuestionSpec
from app.assessments.errors import GenerationFailedError, NoQuestionSourceError
from app.assessments.grading import Criterion
from app.models.enums import AssessmentType, Difficulty, QuestionType

_MCQ = QuestionType.MULTIPLE_CHOICE
_SHORT = QuestionType.SHORT_ANSWER
_CODING = QuestionType.CODING


class QuestionGenerator(Protocol):
    source: str

    async def generate(
        self, skill_slug: str, skill_name: str, assessment_type: AssessmentType, count: int
    ) -> list[QuestionSpec]: ...


def select_from_bank(pool: list[QuestionSpec], assessment_type: AssessmentType, count: int) -> list[QuestionSpec]:
    """Deterministic selection/order. QUIZ = MCQ then short answers; CODING = coding only; MIXED interleaves
    kinds so a small count still contains every kind."""
    mcq = [q for q in pool if q.type == _MCQ]
    short = [q for q in pool if q.type == _SHORT]
    coding = [q for q in pool if q.type == _CODING]
    if assessment_type == AssessmentType.CODING:
        ordered = coding
    elif assessment_type == AssessmentType.QUIZ:
        ordered = mcq + short
    else:
        ordered = []
        for group in (mcq, short, coding):
            ordered.extend(group[:1])
        ordered.extend(mcq[1:])
        ordered.extend(short[1:])
        ordered.extend(coding[1:])
    return ordered[:count]


class BankGenerator:
    source = "demo_bank"

    async def generate(
        self, skill_slug: str, skill_name: str, assessment_type: AssessmentType, count: int
    ) -> list[QuestionSpec]:
        pool = BANK.get(skill_slug)
        if not pool:
            raise NoQuestionSourceError(skill_slug)
        return select_from_bank(pool, assessment_type, count)


class _DraftCriterion(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    any_of: list[str] = Field(min_length=1, max_length=8)


class _DraftQuestion(BaseModel):
    type: QuestionType
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    text: str = Field(min_length=10, max_length=1000)
    options: list[str] | None = None
    correct_option: str | None = None
    criteria: list[_DraftCriterion] | None = Field(default=None, max_length=6)

    @model_validator(mode="after")
    def _check(self):
        if self.type == _MCQ:
            if not self.options or len(self.options) != 4:
                raise ValueError("multiple-choice questions need exactly 4 options")
            if (self.correct_option or "").strip().upper() not in {"A", "B", "C", "D"}:
                raise ValueError("correct_option must be A, B, C or D")
        elif not self.criteria:
            raise ValueError("short-answer and coding questions need at least one rubric criterion")
        return self


class LLMDraftAssessment(BaseModel):
    questions: list[_DraftQuestion] = Field(min_length=1, max_length=10)


_SYSTEM = (
    "You write assessment questions for a learning platform. Return only the requested structure. "
    "Questions must be factual, unambiguous and answerable without internet access. Multiple-choice questions "
    "have exactly 4 options and one correct option letter (A-D). Short-answer and coding questions carry a "
    "rubric: each criterion has a label and a list of lowercase keywords/phrases (any one present means the "
    "criterion is met). Coding rubrics must be checkable by text presence only, because submitted code is "
    "never executed."
)


class LLMGenerator:
    source = "llm"

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    async def generate(
        self, skill_slug: str, skill_name: str, assessment_type: AssessmentType, count: int
    ) -> list[QuestionSpec]:
        kinds = {
            AssessmentType.QUIZ: "multiple-choice and short-answer questions",
            AssessmentType.CODING: "coding challenges",
            AssessmentType.MIXED: "a mix of multiple-choice, short-answer and coding questions",
        }[assessment_type]
        user = f"Write {count} {kinds} that test practical knowledge of: {skill_name}."
        try:
            draft = await self._provider.generate_structured(_SYSTEM, user, LLMDraftAssessment)
        except (AgentError, ValidationError) as exc:
            raise GenerationFailedError(f"The LLM provider could not draft questions: {exc}") from exc
        specs = [self._to_spec(q) for q in draft.questions][:count]
        if assessment_type == AssessmentType.CODING:
            specs = [s for s in specs if s.type == _CODING]
        if not specs:
            raise GenerationFailedError("The LLM provider returned no usable questions")
        return specs

    @staticmethod
    def _to_spec(q: _DraftQuestion) -> QuestionSpec:
        criteria = tuple(Criterion(c.label, tuple(c.any_of)) for c in (q.criteria or []))
        return QuestionSpec(
            type=q.type,
            difficulty=q.difficulty,
            text=q.text,
            options=tuple(q.options or ()),
            correct=(q.correct_option or "").strip().upper() or None,
            criteria=criteria,
        )
