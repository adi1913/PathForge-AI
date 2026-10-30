class MentorError(Exception):
    def __init__(self, message: str, *, code: str = "mentor_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class SessionNotFoundError(MentorError):
    """Also raised for another user's session, so existence is never leaked."""

    def __init__(self):
        super().__init__("Mentor session not found", code="session_not_found", status_code=404)


class MentorUserNotFoundError(MentorError):
    def __init__(self, user_id: str):
        super().__init__(f"User '{user_id}' was not found", code="user_not_found", status_code=404)


class MessageTooLongError(MentorError):
    def __init__(self, limit: int):
        super().__init__(f"Message exceeds the {limit}-character limit", code="message_too_long", status_code=422)
