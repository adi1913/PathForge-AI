from sqlalchemy.orm import Session

from app.assessments.errors import AssessmentNotFoundError, AttemptNotFoundError
from app.models.assessment import Assessment, AssessmentAttempt


def load_owned_assessment(db: Session, assessment_id: str, user_id: str) -> Assessment:
    """Unknown id and someone else's assessment are indistinguishable (404)."""
    row = db.query(Assessment).filter_by(id=assessment_id, user_id=user_id).one_or_none()
    if row is None:
        raise AssessmentNotFoundError()
    return row


def load_owned_attempt(db: Session, attempt_id: str, user_id: str) -> AssessmentAttempt:
    """An attempt is owned by the user who started it AND must sit on an assessment that user owns."""
    row = db.query(AssessmentAttempt).filter_by(id=attempt_id, user_id=user_id).one_or_none()
    if row is None or row.assessment.user_id != user_id:
        raise AttemptNotFoundError()
    return row
