"""Assessment generation, attempts, deterministic grading, evidence ledger and confidence updates.
See docs/phase12_spec.md. Never changes UserSkill.level / UserSkill.source."""

import hashlib
import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.errors import AgentError
from app.agent.llm.factory import get_llm_provider
from app.assessments import grading
from app.assessments.access import load_owned_assessment, load_owned_attempt
from app.assessments.adaptation import AdaptationService
from app.assessments.bank import QuestionSpec
from app.assessments.errors import (
    AssessmentError,
    AttemptAlreadySubmittedError,
    InvalidSubmissionError,
    NoSkillSpecifiedError,
    RoadmapItemForAssessmentError,
    SkillNotFoundError,
    UserNotFoundError,
)
from app.assessments.generator import BankGenerator, LLMGenerator, QuestionGenerator
from app.assessments.rules import RULES_VERSION, ConfidenceUpdate, classify_outcome, compute_confidence_update
from app.assessments.schemas import (
    GRADING_NOTICE,
    SOURCE_LABELS,
    AdaptationOut,
    AnswerEvaluation,
    AnswerResult,
    AssessmentListItem,
    AssessmentOut,
    AttemptStartOut,
    AttemptStartRequest,
    ConfidenceOut,
    EvidenceOut,
    GenerateRequest,
    OptionOut,
    QuestionOut,
    SubmitOut,
    SubmitRequest,
)
from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.models.assessment import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentEvidence,
    Question,
)
from app.models.enums import AssessmentOutcome, ProgressEventType, QuestionType
from app.models.progress import ProgressEvent
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import Skill, UserSkill
from app.models.user import User
from app.roadmap.errors import RoadmapError

logger = logging.getLogger("pathforge.assessments")

_MAX_ASSESSMENT_EVIDENCE_ENTRIES = 5


def question_set_hash(questions: list[Question]) -> str:
    joined = "\n".join(q.question_text for q in sorted(questions, key=lambda q: q.order_index))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def to_question_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        order_index=q.order_index,
        question_type=q.question_type,
        difficulty=q.difficulty,
        text=q.question_text,
        options=[OptionOut(id=o["id"], text=o["text"]) for o in (q.options or [])] or None,
    )


def to_assessment_out(a: Assessment) -> AssessmentOut:
    skill = a.skill
    return AssessmentOut(
        id=a.id,
        user_id=a.user_id,
        skill_slug=skill.slug if skill else None,
        skill_name=skill.name if skill else None,
        roadmap_item_id=a.roadmap_item_id,
        title=a.title,
        assessment_type=a.assessment_type,
        generation_source=a.generation_source,
        source_label=SOURCE_LABELS.get(a.generation_source, a.generation_source),
        questions=[to_question_out(q) for q in sorted(a.questions, key=lambda q: q.order_index)],
        created_at=a.created_at,
    )


class AssessmentService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        generator: QuestionGenerator | None = None,
    ):
        self._db = db
        self._settings = settings or get_settings()
        self._generator = generator

    # --- generate / fetch -----------------------------------------------------------------------

    async def generate(self, request: GenerateRequest) -> AssessmentOut:
        if self._db.get(User, request.user_id) is None:
            raise UserNotFoundError(request.user_id)
        skill, item = self._resolve_skill(request)
        specs = await self._get_generator().generate(
            skill.slug, skill.name, request.assessment_type, request.question_count
        )
        source = self._get_generator().source
        assessment = Assessment(
            user_id=request.user_id,
            roadmap_item_id=item.id if item else None,
            skill_id=skill.id,
            title=f"{skill.name} {request.assessment_type.value} assessment",
            assessment_type=request.assessment_type,
            generation_source=source,
        )
        self._db.add(assessment)
        self._db.flush()
        for index, spec in enumerate(specs):
            self._db.add(self._to_question(assessment.id, index, spec))
        self._db.commit()
        self._db.refresh(assessment)
        logger.info(
            "Assessment generated: type=%s questions=%d source=%s", request.assessment_type.value, len(specs), source
        )
        return to_assessment_out(assessment)

    def get(self, assessment_id: str, user_id: str) -> AssessmentOut:
        return to_assessment_out(load_owned_assessment(self._db, assessment_id, user_id))

    def list_assessments(self, user_id: str, skill_slug: str | None = None) -> list[AssessmentListItem]:
        query = self._db.query(Assessment).filter_by(user_id=user_id)
        if skill_slug:
            query = query.join(Skill, Skill.id == Assessment.skill_id).filter(Skill.slug == skill_slug)
        rows = query.order_by(Assessment.created_at.desc(), Assessment.id).all()
        return [
            AssessmentListItem(
                id=a.id,
                title=a.title,
                skill_slug=a.skill.slug if a.skill else None,
                assessment_type=a.assessment_type,
                generation_source=a.generation_source,
                question_count=len(a.questions),
                attempts=len(a.attempts),
                created_at=a.created_at,
            )
            for a in rows
        ]

    def _get_generator(self) -> QuestionGenerator:
        if self._generator is None:
            if self._settings.DEMO_MODE:
                self._generator = BankGenerator()
            else:
                try:
                    self._generator = LLMGenerator(get_llm_provider(self._settings))
                except (AgentError, NotImplementedError) as exc:
                    raise AssessmentError(str(exc), code="llm_unavailable", status_code=503) from exc
        return self._generator

    def _resolve_skill(self, request: GenerateRequest) -> tuple[Skill, RoadmapItem | None]:
        item = None
        if request.roadmap_item_id:
            item = (
                self._db.query(RoadmapItem)
                .join(Roadmap, Roadmap.id == RoadmapItem.roadmap_id)
                .filter(RoadmapItem.id == request.roadmap_item_id, Roadmap.user_id == request.user_id)
                .one_or_none()
            )
            if item is None:
                raise RoadmapItemForAssessmentError()
            if item.skill_id is None:
                raise NoSkillSpecifiedError()
        if item is not None and request.skill_slug is None:
            skill = self._db.get(Skill, item.skill_id)
        elif request.skill_slug:
            skill = self._db.query(Skill).filter_by(slug=request.skill_slug).one_or_none()
            if skill is None:
                raise SkillNotFoundError(request.skill_slug)
            if item is not None and item.skill_id != skill.id:
                raise AssessmentError(
                    "skill_slug does not match the skill of the roadmap item", code="skill_mismatch", status_code=422
                )
        else:
            raise NoSkillSpecifiedError()
        return skill, item

    @staticmethod
    def _to_question(assessment_id: str, index: int, spec: QuestionSpec) -> Question:
        mcq = spec.type == QuestionType.MULTIPLE_CHOICE
        return Question(
            assessment_id=assessment_id,
            order_index=index,
            question_text=spec.text,
            question_type=spec.type,
            difficulty=spec.difficulty,
            options=[{"id": "ABCD"[i], "text": t} for i, t in enumerate(spec.options)] if mcq else None,
            expected_answer=spec.correct if mcq else None,
            evaluation_rubric=None if mcq else grading.dump_rubric(list(spec.criteria)),
        )

    # --- attempts -------------------------------------------------------------------------------

    def start_attempt(self, assessment_id: str, request: AttemptStartRequest) -> AttemptStartOut:
        assessment = load_owned_assessment(self._db, assessment_id, request.user_id)
        open_attempt = (
            self._db.query(AssessmentAttempt)
            .filter_by(assessment_id=assessment.id, user_id=request.user_id, completed_at=None)
            .order_by(AssessmentAttempt.started_at, AssessmentAttempt.id)
            .first()
        )
        resumed = open_attempt is not None
        attempt = open_attempt or AssessmentAttempt(
            assessment_id=assessment.id, user_id=request.user_id, started_at=utcnow()
        )
        if not resumed:
            self._db.add(attempt)
            self._db.commit()
            self._db.refresh(attempt)
        return AttemptStartOut(
            attempt_id=attempt.id,
            assessment_id=assessment.id,
            started_at=attempt.started_at,
            resumed=resumed,
            questions=[to_question_out(q) for q in sorted(assessment.questions, key=lambda q: q.order_index)],
        )

    def submit(self, attempt_id: str, request: SubmitRequest) -> SubmitOut:
        attempt = load_owned_attempt(self._db, attempt_id, request.user_id)
        if attempt.completed_at is not None:
            raise AttemptAlreadySubmittedError()
        assessment = attempt.assessment
        questions = sorted(assessment.questions, key=lambda q: q.order_index)
        given = self._validate_answers(questions, request)

        graded: list[tuple[Question, grading.GradedAnswer]] = [
            (q, grading.grade_answer(q.question_type, q.expected_answer, q.evaluation_rubric, given.get(q.id)))
            for q in questions
        ]
        score_percent = grading.weighted_score_percent([(q.question_type, g.score) for q, g in graded])
        outcome = classify_outcome(score_percent, len(questions))
        methods = sorted({g.evaluation["method"] for _, g in graded})
        attempt_number = (
            self._db.query(AssessmentAttempt)
            .filter(AssessmentAttempt.assessment_id == assessment.id, AssessmentAttempt.completed_at.is_not(None))
            .count()
            + 1
        )

        for q, g in graded:
            self._db.add(
                AssessmentAnswer(
                    attempt_id=attempt.id,
                    question_id=q.id,
                    answer=given.get(q.id),
                    is_correct=g.is_correct,
                    score=round(g.score * 100, 1),
                    feedback=g.feedback,
                    evaluation=g.evaluation,
                )
            )
        attempt.score = score_percent
        attempt.completed_at = utcnow()

        evidence = None
        is_retake = False
        update = ConfidenceUpdate(
            None, None, 0.0, "This assessment is not linked to a skill; no evidence was recorded."
        )
        if assessment.skill_id is not None:
            update, evidence, is_retake = self._record_evidence(
                assessment, attempt, questions, outcome, score_percent, methods, attempt_number
            )
        self._record_progress_event(assessment, attempt, outcome, score_percent)
        self._db.commit()

        adaptation = AdaptationOut(roadmap_id=None, actions=[], replanned=False, warnings=[])
        if outcome in (AssessmentOutcome.STRONG, AssessmentOutcome.WEAK):
            try:
                adaptation = AdaptationService(self._db, self._settings).adapt(assessment, outcome, attempt.id)
            except (RoadmapError, SQLAlchemyError) as exc:  # the graded result is already committed; keep it
                self._db.rollback()
                logger.error("Roadmap adaptation failed: %s", type(exc).__name__)
                adaptation = AdaptationOut(
                    roadmap_id=None,
                    actions=[],
                    replanned=False,
                    warnings=["Your result was saved, but the roadmap could not be adapted."],
                )
        logger.info("Attempt graded: outcome=%s score=%.1f questions=%d", outcome.value, score_percent, len(questions))

        return SubmitOut(
            attempt_id=attempt.id,
            assessment_id=assessment.id,
            skill_slug=assessment.skill.slug if assessment.skill else None,
            score_percent=score_percent,
            outcome=outcome,
            attempt_number=attempt_number,
            is_retake=is_retake,
            generation_source=assessment.generation_source,
            evaluation_methods=methods,
            answers=[self._answer_result(q, g) for q, g in graded],
            confidence=ConfidenceOut(
                applied=update.delta_applied != 0.0,
                before=update.before,
                after=update.after,
                delta=update.delta_applied,
                note=update.note,
            ),
            adaptation=adaptation,
            notices=self._notices(assessment, questions),
            evidence_id=evidence.id if evidence else None,
        )

    def _validate_answers(self, questions: list[Question], request: SubmitRequest) -> dict[str, str]:
        by_id = {q.id: q for q in questions}
        given: dict[str, str] = {}
        for item in request.answers:
            q = by_id.get(item.question_id)
            if q is None:
                raise InvalidSubmissionError("An answer refers to a question that is not part of this assessment")
            if item.question_id in given:
                raise InvalidSubmissionError("Each question can be answered only once")
            limit = (
                self._settings.ASSESSMENT_MAX_CODE_CHARS
                if q.question_type == QuestionType.CODING
                else self._settings.ASSESSMENT_MAX_ANSWER_CHARS
            )
            if len(item.answer) > limit:
                raise InvalidSubmissionError(f"An answer exceeds the {limit}-character limit for its question type")
            given[item.question_id] = item.answer
        return given

    def _record_evidence(
        self,
        assessment: Assessment,
        attempt: AssessmentAttempt,
        questions: list[Question],
        outcome: AssessmentOutcome,
        score_percent: float,
        methods: list[str],
        attempt_number: int,
    ) -> tuple[ConfidenceUpdate, AssessmentEvidence, bool]:
        user_id, skill_id = assessment.user_id, assessment.skill_id
        qhash = question_set_hash(questions)
        prior = self._db.query(AssessmentEvidence).filter_by(user_id=user_id, skill_id=skill_id).all()
        is_retake = any(row.question_set_hash == qhash for row in prior)
        user_skill = self._db.get(UserSkill, (user_id, skill_id))
        update = compute_confidence_update(
            outcome=outcome,
            score_percent=score_percent,
            coding_only=all(q.question_type == QuestionType.CODING for q in questions),
            is_retake=is_retake,
            confidence_before=user_skill.confidence if user_skill else None,
            has_user_skill=user_skill is not None,
            net_so_far=sum(row.confidence_delta_applied for row in prior),
        )
        row = AssessmentEvidence(
            user_id=user_id,
            skill_id=skill_id,
            assessment_id=assessment.id,
            attempt_id=attempt.id,
            attempt_number=attempt_number,
            score_percent=score_percent,
            outcome=outcome,
            assessment_type=assessment.assessment_type.value,
            question_count=len(questions),
            evaluation_methods=methods,
            confidence_before=update.before,
            confidence_after=update.after,
            confidence_delta_applied=update.delta_applied,
            confidence_note=update.note[:300],
            rules_version=RULES_VERSION,
            question_set_hash=qhash,
            data_source=assessment.generation_source,
        )
        self._db.add(row)
        if user_skill is not None and update.delta_applied != 0.0:
            user_skill.confidence = update.after  # confidence only: level and source are never written
            entry = {
                "type": "assessment",
                "assessment_id": assessment.id,
                "attempt_id": attempt.id,
                "score_percent": score_percent,
                "outcome": outcome.value,
                "confidence_delta": update.delta_applied,
                "at": utcnow().isoformat(),
            }
            existing = list(user_skill.evidence or [])
            others = [e for e in existing if not (isinstance(e, dict) and e.get("type") == "assessment")]
            mine = [e for e in existing if isinstance(e, dict) and e.get("type") == "assessment"]
            user_skill.evidence = others + [*mine, entry][-_MAX_ASSESSMENT_EVIDENCE_ENTRIES:]
        self._db.flush()
        return update, row, is_retake

    def _record_progress_event(
        self, assessment: Assessment, attempt: AssessmentAttempt, outcome: AssessmentOutcome, score_percent: float
    ) -> None:
        if outcome == AssessmentOutcome.INSUFFICIENT:
            return
        item = self._db.get(RoadmapItem, assessment.roadmap_item_id) if assessment.roadmap_item_id else None
        passed = outcome in (AssessmentOutcome.STRONG, AssessmentOutcome.PASSED)
        self._db.add(
            ProgressEvent(
                user_id=assessment.user_id,
                roadmap_item_id=item.id if item else None,
                event_type=ProgressEventType.ASSESSMENT_PASSED if passed else ProgressEventType.ASSESSMENT_FAILED,
                previous_value=None,
                new_value=f"{score_percent:g}%",
                event_metadata={
                    "assessment_id": assessment.id,
                    "attempt_id": attempt.id,
                    "outcome": outcome.value,
                    "roadmap_id": item.roadmap_id if item else None,
                },
            )
        )

    @staticmethod
    def _answer_result(q: Question, g: grading.GradedAnswer) -> AnswerResult:
        ev = g.evaluation
        return AnswerResult(
            question_id=q.id,
            question_type=q.question_type,
            is_correct=g.is_correct,
            score_percent=round(g.score * 100, 1),
            feedback=g.feedback,
            evaluation=AnswerEvaluation(
                method=ev["method"],
                notice=ev.get("notice"),
                executed=ev.get("executed"),
                criteria_met=ev.get("criteria_met"),
                criteria_total=ev.get("criteria_total"),
            ),
        )

    @staticmethod
    def _notices(assessment: Assessment, questions: list[Question]) -> list[str]:
        notices = [SOURCE_LABELS.get(assessment.generation_source, ""), GRADING_NOTICE]
        if any(q.question_type == QuestionType.CODING for q in questions):
            notices.append(grading.CODING_NOTICE)
        notices.append("Assessment results only adjust skill confidence; your recorded skill level was not changed.")
        return [n for n in notices if n]

    # --- evidence history -----------------------------------------------------------------------

    def evidence(self, user_id: str, skill_slug: str | None = None) -> list[EvidenceOut]:
        query = self._db.query(AssessmentEvidence).filter_by(user_id=user_id)
        if skill_slug:
            query = query.join(Skill, Skill.id == AssessmentEvidence.skill_id).filter(Skill.slug == skill_slug)
        rows = query.order_by(AssessmentEvidence.created_at.desc(), AssessmentEvidence.id).all()
        skills = (
            {s.id: s for s in self._db.query(Skill).filter(Skill.id.in_({r.skill_id for r in rows}))} if rows else {}
        )
        return [
            EvidenceOut(
                id=r.id,
                skill_slug=skills[r.skill_id].slug,
                skill_name=skills[r.skill_id].name,
                assessment_id=r.assessment_id,
                attempt_id=r.attempt_id,
                attempt_number=r.attempt_number,
                score_percent=r.score_percent,
                outcome=r.outcome,
                assessment_type=r.assessment_type,
                question_count=r.question_count,
                evaluation_methods=list(r.evaluation_methods),
                confidence_before=r.confidence_before,
                confidence_after=r.confidence_after,
                confidence_delta_applied=r.confidence_delta_applied,
                confidence_note=r.confidence_note,
                rules_version=r.rules_version,
                data_source=r.data_source,
                created_at=r.created_at,
            )
            for r in rows
        ]
