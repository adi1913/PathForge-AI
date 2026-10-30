from sqlalchemy.orm import Session

from app.models.roadmap import Roadmap
from app.roadmap.errors import RoadmapNotFoundError


def load_owned_roadmap(db: Session, roadmap_id: str, user_id: str) -> Roadmap:
    """Unknown id and someone else's roadmap are indistinguishable (404)."""
    roadmap = db.query(Roadmap).filter_by(id=roadmap_id, user_id=user_id).one_or_none()
    if roadmap is None:
        raise RoadmapNotFoundError()
    return roadmap
