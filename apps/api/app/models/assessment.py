from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin, utcnow
from app.models.enums import AssessmentOutcome, AssessmentType, Difficulty, QuestionType


class Assessment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "assessments"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    roadmap_item_id: Mapped[str | None] = mapped_column(ForeignKey("roadmap_items.id", ondelete="SET NULL"), index=True)
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    assessment_type: Mapped[AssessmentType] = mapped_column(
        Enum(AssessmentType, native_enum=False, length=20), default=AssessmentType.QUIZ, nullable=False
    )
    # Phase 12: "demo_bank" (fixed, deterministic fixture questions) or "llm" (drafted by the
    # configured LLM provider). Always surfaced to the user so demo questions are never passed off as live.
    generation_source: Mapped[str] = mapped_column(
        String(20), default="demo_bank", server_default="demo_bank", nullable=False
    )

    skill: Mapped["Skill | None"] = relationship()
    questions: Mapped[list["Question"]] = relationship(back_populates="assessment", cascade="all, delete-orphan")
    attempts: Mapped[list["AssessmentAttempt"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class Question(UUIDPKMixin, TimestampMixin, Base):
    """`expected_answer` and `evaluation_rubric` are answer-key data.
    They must never be serialized into a user-facing API response — the
    Phase-2 boundary for that is simply "no Pydantic schema for Question
    includes these fields"; enforced for real once the assessment API
    endpoints exist (Phase 11)."""

    __tablename__ = "questions"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False, length=20), nullable=False
    )
    difficulty: Mapped[Difficulty | None] = mapped_column(Enum(Difficulty, native_enum=False, length=20))
    options: Mapped[list | None] = mapped_column(JSON)  # for multiple_choice
    expected_answer: Mapped[str | None] = mapped_column(Text)  # ANSWER KEY — never expose via API
    evaluation_rubric: Mapped[str | None] = mapped_column(Text)  # ANSWER KEY — never expose via API

    assessment: Mapped["Assessment"] = relationship(back_populates="questions")
    answers: Mapped[list["AssessmentAnswer"]] = relationship(back_populates="question")


class AssessmentAttempt(UUIDPKMixin, Base):
    __tablename__ = "assessment_attempts"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assessment: Mapped["Assessment"] = relationship(back_populates="attempts")
    user: Mapped["User"] = relationship(back_populates="assessment_attempts")
    answers: Mapped[list["AssessmentAnswer"]] = relationship(back_populates="attempt", cascade="all, delete-orphan")


class AssessmentAnswer(UUIDPKMixin, Base):
    __tablename__ = "assessment_answers"

    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column()
    score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(Text)
    # Phase 12: {"method": ..., "executed": false, "criteria_met": n, "criteria_total": n} — never the key.
    evaluation: Mapped[dict | None] = mapped_column(JSON)

    attempt: Mapped["AssessmentAttempt"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship(back_populates="answers")


class AssessmentEvidence(UUIDPKMixin, Base):
    """Append-only ledger: one immutable row per graded attempt. Independent of UserSkill, so resume
    re-analysis (which rewrites UserSkill) can never overwrite or erase assessment results. Nothing in
    the application updates or deletes these rows; attempt/assessment deletion only nulls the links."""

    __tablename__ = "assessment_evidence"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_assessment_evidence_attempt"),
        Index("ix_assessment_evidence_user_skill", "user_id", "skill_id"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id", ondelete="SET NULL"), index=True)
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_attempts.id", ondelete="SET NULL"))
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    score_percent: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[AssessmentOutcome] = mapped_column(
        Enum(AssessmentOutcome, native_enum=False, length=20), nullable=False
    )
    assessment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_methods: Mapped[list] = mapped_column(JSON, nullable=False)
    confidence_before: Mapped[float | None] = mapped_column(Float)
    confidence_after: Mapped[float | None] = mapped_column(Float)
    confidence_delta_applied: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence_note: Mapped[str] = mapped_column(String(300), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # sha256 of the question texts: the same question set (even in a re-generated assessment) is a retake.
    question_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), nullable=False)  # demo_bank | llm
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
