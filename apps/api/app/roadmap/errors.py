class RoadmapError(Exception):
    def __init__(self, message: str, *, code: str = "roadmap_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class UserNotFoundError(RoadmapError):
    def __init__(self, user_id: str):
        super().__init__(f"User '{user_id}' was not found", code="user_not_found", status_code=404)


class NoOpenSkillGapsError(RoadmapError):
    def __init__(self):
        super().__init__(
            "No open skill gaps to plan from — run a job description analysis for this user first",
            code="no_open_gaps",
            status_code=409,
        )


class RoadmapNotFoundError(RoadmapError):
    """Also raised for another user's roadmap, so existence is never leaked."""

    def __init__(self):
        super().__init__("Roadmap not found", code="roadmap_not_found", status_code=404)


class RoadmapItemNotFoundError(RoadmapError):
    def __init__(self):
        super().__init__("Roadmap item not found", code="roadmap_item_not_found", status_code=404)


class RoadmapArchivedError(RoadmapError):
    def __init__(self):
        super().__init__(
            "This roadmap is archived and can no longer be changed; use the active roadmap",
            code="roadmap_archived",
            status_code=409,
        )


class InvalidTransitionError(RoadmapError):
    def __init__(self, message: str):
        super().__init__(message, code="invalid_transition", status_code=409)


class InvalidProgressInputError(RoadmapError):
    def __init__(self, message: str):
        super().__init__(message, code="invalid_progress_input", status_code=422)


class NothingToReplanError(RoadmapError):
    def __init__(self):
        super().__init__(
            "Every skill on this roadmap is already completed or skipped; there is nothing left to re-plan",
            code="nothing_to_replan",
            status_code=409,
        )
