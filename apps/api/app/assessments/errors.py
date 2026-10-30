class AssessmentError(Exception):
    def __init__(self, message: str, *, code: str = "assessment_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class AssessmentNotFoundError(AssessmentError):
    """Also raised for another user's assessment, so existence is never leaked."""

    def __init__(self):
        super().__init__("Assessment not found", code="assessment_not_found", status_code=404)


class AttemptNotFoundError(AssessmentError):
    """Also raised for another user's attempt."""

    def __init__(self):
        super().__init__("Attempt not found", code="attempt_not_found", status_code=404)


class UserNotFoundError(AssessmentError):
    def __init__(self, user_id: str):
        super().__init__(f"User '{user_id}' was not found", code="user_not_found", status_code=404)


class SkillNotFoundError(AssessmentError):
    def __init__(self, slug: str):
        super().__init__(f"Skill '{slug}' is not in the skill catalog", code="skill_not_found", status_code=404)


class NoSkillSpecifiedError(AssessmentError):
    def __init__(self):
        super().__init__(
            "Provide skill_slug or a roadmap_item_id that belongs to a skill", code="no_skill", status_code=422
        )


class RoadmapItemForAssessmentError(AssessmentError):
    """Unknown or foreign roadmap item: same 404 either way."""

    def __init__(self):
        super().__init__("Roadmap item not found", code="roadmap_item_not_found", status_code=404)


class NoQuestionSourceError(AssessmentError):
    def __init__(self, slug: str):
        super().__init__(
            f"The demo question bank has no questions for skill '{slug}'. Set DEMO_MODE=false with a configured "
            "LLM provider to draft questions for it.",
            code="no_question_bank",
            status_code=422,
        )


class GenerationFailedError(AssessmentError):
    def __init__(self, message: str):
        super().__init__(message, code="generation_failed", status_code=502)


class AttemptAlreadySubmittedError(AssessmentError):
    def __init__(self):
        super().__init__("This attempt was already submitted", code="attempt_already_submitted", status_code=409)


class InvalidSubmissionError(AssessmentError):
    def __init__(self, message: str):
        super().__init__(message, code="invalid_submission", status_code=422)
