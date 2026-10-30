from sqlalchemy.orm import Session

from app.mentor.errors import SessionNotFoundError
from app.models.mentor import MentorSession


def load_owned_session(db: Session, session_id: str, user_id: str) -> MentorSession:
    """Unknown id and someone else's session are indistinguishable (404)."""
    row = db.query(MentorSession).filter_by(id=session_id, user_id=user_id).one_or_none()
    if row is None:
        raise SessionNotFoundError()
    return row
