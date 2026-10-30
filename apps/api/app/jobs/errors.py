class JobDescriptionError(Exception):
    def __init__(self, message: str, *, code: str = "job_description_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class UnsupportedJDFormatError(JobDescriptionError):
    def __init__(self, content_type: str):
        super().__init__(f"Unsupported job description format: '{content_type}'", code="unsupported_format")


class JDTooLargeError(JobDescriptionError):
    def __init__(self, message: str):
        super().__init__(message, code="jd_too_large")
