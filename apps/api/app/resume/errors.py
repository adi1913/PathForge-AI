class ResumeError(Exception):
    def __init__(self, message: str, *, code: str = "resume_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class UnsupportedResumeFormatError(ResumeError):
    def __init__(self, content_type: str):
        super().__init__(f"Unsupported resume format: '{content_type}'", code="unsupported_format")


class ResumeTooLargeError(ResumeError):
    def __init__(self, message: str):
        super().__init__(message, code="resume_too_large")


class ResumeParsingFailedError(ResumeError):
    """Raised only when extraction produced nothing usable at all (e.g. a
    scanned-image PDF with zero extractable text) — a real limitation to
    report, never silently treated as an empty-but-successful resume."""

    def __init__(self, message: str):
        super().__init__(message, code="parsing_failed")
