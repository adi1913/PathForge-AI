import pytest

from app.assessments.errors import (
    AssessmentNotFoundError,
    AttemptAlreadySubmittedError,
    AttemptNotFoundError,
    InvalidSubmissionError,
    NoQuestionSourceError,
    NoSkillSpecifiedError,
    RoadmapItemForAssessmentError,
    SkillNotFoundError,
)
from app.assessments.schemas import AnswerIn, AttemptStartRequest, GenerateRequest, SubmitRequest
from app.assessments.service import AssessmentService
from app.models.assessment import AssessmentAnswer, AssessmentEvidence
from app.models.enums import EvidenceSource, ProgressEventType, SkillLevel
from app.models.progress import ProgressEvent
from app.models.skill import UserSkill
from tests.test_assessments.helpers import answers_for, generate, own, run_attempt, seed


async def test_generate_is_labelled_demo_and_has_no_keys(db_session):
    user, _, skills = seed(db_session)
    out = await generate(db_session, user, "rag", "mixed", 7)
    assert out.generation_source == "demo_bank" and "Demo question bank" in out.source_label
    assert [q.order_index for q in out.questions] == list(range(7))
    dumped = out.model_dump_json()
    assert "expected_answer" not in dumped and "any_of" not in dumped
    kinds = {q.question_type.value for q in out.questions}
    assert kinds == {"multiple_choice", "short_answer", "coding"}


async def test_generate_validation_errors(db_session):
    user, other, skills = seed(db_session)
    service = AssessmentService(db_session)
    with pytest.raises(NoQuestionSourceError):
        await generate(db_session, user, "git", service=service)
    with pytest.raises(SkillNotFoundError):
        await generate(db_session, user, "nope", service=service)
    with pytest.raises(NoSkillSpecifiedError):
        await service.generate(GenerateRequest(user_id=user.id))
    with pytest.raises(RoadmapItemForAssessmentError):
        await service.generate(GenerateRequest(user_id=user.id, roadmap_item_id="missing"))


async def test_ownership_unknown_equals_foreign(db_session):
    user, other, _ = seed(db_session)
    a = await generate(db_session, user)
    service = AssessmentService(db_session)
    with pytest.raises(AssessmentNotFoundError):
        service.get(a.id, other.id)
    with pytest.raises(AssessmentNotFoundError):
        service.get("unknown", user.id)
    with pytest.raises(AssessmentNotFoundError):
        service.start_attempt(a.id, AttemptStartRequest(user_id=other.id))
    started = service.start_attempt(a.id, AttemptStartRequest(user_id=user.id))
    with pytest.raises(AttemptNotFoundError):
        service.submit(started.attempt_id, SubmitRequest(user_id=other.id, answers=[]))
    assert service.list_assessments(other.id) == []


async def test_start_attempt_resumes_open_attempt(db_session):
    user, _, _ = seed(db_session)
    a = await generate(db_session, user)
    service = AssessmentService(db_session)
    first = service.start_attempt(a.id, AttemptStartRequest(user_id=user.id))
    again = service.start_attempt(a.id, AttemptStartRequest(user_id=user.id))
    assert not first.resumed and again.resumed and first.attempt_id == again.attempt_id


async def test_strong_result_raises_confidence_only(db_session):
    user, _, skills = seed(db_session)
    row = own(db_session, user, skills["rag"], SkillLevel.INTERMEDIATE, 0.6)
    a = await generate(db_session, user, "rag")
    result = await run_attempt(db_session, user, a.id, "correct")
    assert result.score_percent == 100 and result.outcome.value == "strong"
    assert result.confidence.applied and result.confidence.after == 0.7 and result.confidence.level_changed is False
    db_session.refresh(row)
    assert row.confidence == 0.7
    assert row.current_level == SkillLevel.INTERMEDIATE and row.source == EvidenceSource.RESUME
    assert any(e.get("type") == "assessment" for e in row.evidence) and row.evidence[0]["type"] == "resume"
    ledger = db_session.query(AssessmentEvidence).one()
    assert (
        ledger.outcome.value == "strong"
        and ledger.confidence_delta_applied == 0.1
        and ledger.data_source == "demo_bank"
    )
    event = db_session.query(ProgressEvent).filter_by(event_type=ProgressEventType.ASSESSMENT_PASSED).one()
    assert event.event_metadata["assessment_id"] == a.id


async def test_weak_result_lowers_confidence_and_is_deterministic(db_session):
    user, _, skills = seed(db_session)
    row = own(db_session, user, skills["rag"], confidence=0.6)
    a1 = await generate(db_session, user, "rag")
    result = await run_attempt(db_session, user, a1.id, "wrong")
    assert result.score_percent == 0 and result.outcome.value == "weak" and result.confidence.delta == -0.1
    db_session.refresh(row)
    assert row.confidence == 0.5
    assert db_session.query(ProgressEvent).filter_by(event_type=ProgressEventType.ASSESSMENT_FAILED).count() == 1


async def test_same_answers_same_score(db_session):
    user, _, skills = seed(db_session)
    a = await generate(db_session, user, "rag")
    r1 = await run_attempt(db_session, user, a.id, "mcq_only")
    r2 = await run_attempt(db_session, user, a.id, "mcq_only")
    assert r1.score_percent == r2.score_percent and [x.score_percent for x in r1.answers] == [
        x.score_percent for x in r2.answers
    ]


async def test_retake_and_regenerated_same_set_do_not_move_confidence(db_session):
    user, _, skills = seed(db_session)
    row = own(db_session, user, skills["rag"], confidence=0.6)
    a = await generate(db_session, user, "rag")
    await run_attempt(db_session, user, a.id, "correct")
    retake = await run_attempt(db_session, user, a.id, "correct")
    assert retake.is_retake and retake.attempt_number == 2 and retake.confidence.delta == 0.0
    regenerated = await generate(db_session, user, "rag")
    again = await run_attempt(db_session, user, regenerated.id, "correct")
    assert again.is_retake and again.confidence.applied is False
    db_session.refresh(row)
    assert row.confidence == 0.7
    assert db_session.query(AssessmentEvidence).count() == 3  # every attempt is kept as evidence


async def test_cumulative_adjustment_is_capped(db_session):
    user, _, skills = seed(db_session)
    row = own(db_session, user, skills["rag"], confidence=0.3)
    for count in (3, 4, 5, 6):  # different question sets -> not retakes
        a = await generate(db_session, user, "rag", "quiz", count)
        await run_attempt(db_session, user, a.id, "correct")
    db_session.refresh(row)
    assert row.confidence == 0.6  # 0.3 + 0.30 cap


async def test_no_user_skill_keeps_evidence_without_creating_row(db_session):
    user, _, skills = seed(db_session)
    a = await generate(db_session, user, "rag")
    result = await run_attempt(db_session, user, a.id, "correct")
    assert not result.confidence.applied and "No level is recorded" in result.confidence.note
    assert db_session.query(UserSkill).count() == 0
    assert db_session.query(AssessmentEvidence).count() == 1


async def test_coding_only_is_insufficient_and_labelled(db_session):
    user, _, skills = seed(db_session)
    row = own(db_session, user, skills["rag"], confidence=0.6)
    a = await generate(db_session, user, "rag", "coding", 3)
    assert len(a.questions) == 1
    result = await run_attempt(db_session, user, a.id, "correct")
    assert result.outcome.value == "insufficient" and result.confidence.delta == 0.0
    coding = result.answers[0].evaluation
    assert coding.executed is False and "not executed" in coding.notice
    assert any("not executed" in n for n in result.notices)
    db_session.refresh(row)
    assert row.confidence == 0.6


async def test_submission_validation(db_session):
    user, _, _ = seed(db_session)
    a = await generate(db_session, user, "rag")
    service = AssessmentService(db_session)
    started = service.start_attempt(a.id, AttemptStartRequest(user_id=user.id))
    qid = a.questions[0].id
    with pytest.raises(InvalidSubmissionError):
        service.submit(
            started.attempt_id, SubmitRequest(user_id=user.id, answers=[AnswerIn(question_id="x", answer="A")])
        )
    with pytest.raises(InvalidSubmissionError):
        service.submit(
            started.attempt_id, SubmitRequest(user_id=user.id, answers=[AnswerIn(question_id=qid, answer="A")] * 2)
        )
    with pytest.raises(InvalidSubmissionError):
        service.submit(
            started.attempt_id, SubmitRequest(user_id=user.id, answers=[AnswerIn(question_id=qid, answer="A" * 6000)])
        )
    service.submit(started.attempt_id, SubmitRequest(user_id=user.id, answers=answers_for(db_session, a.id, "correct")))
    with pytest.raises(AttemptAlreadySubmittedError):
        service.submit(started.attempt_id, SubmitRequest(user_id=user.id, answers=[]))
    assert db_session.query(AssessmentAnswer).count() == len(a.questions)


async def test_submit_response_never_contains_key_material(db_session):
    user, _, skills = seed(db_session)
    own(db_session, user, skills["rag"])
    a = await generate(db_session, user, "rag", "mixed", 7)
    result = await run_attempt(db_session, user, a.id, "wrong")
    blob = result.model_dump_json().lower()
    from app.assessments.bank import BANK

    for spec in BANK["rag"]:
        for criterion in spec.criteria:
            assert criterion.label.lower() not in blob
            for pattern in criterion.any_of:
                if len(pattern) >= 12:
                    assert pattern.lower() not in blob
    history = AssessmentService(db_session).evidence(user.id)
    assert "expected" not in " ".join(h.model_dump_json() for h in history)
