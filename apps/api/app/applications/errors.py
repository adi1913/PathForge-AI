class ApplicationError(Exception):
    def __init__(self, message: str, *, code: str = "application_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ApplicationNotFoundError(ApplicationError):
    """Also raised for another user's application, so existence is never leaked."""

    def __init__(self):
        super().__init__("Application not found", code="application_not_found", status_code=404)


class ReferenceNotFoundError(ApplicationError):
    def __init__(self, what: str):
        super().__init__(f"{what} not found", code="reference_not_found", status_code=404)


class DuplicateApplicationError(ApplicationError):
    def __init__(self):
        super().__init__(
            "An application for this job description already exists", code="duplicate_application", status_code=409
        )


class InvalidStatusTransitionError(ApplicationError):
    def __init__(self, message: str):
        super().__init__(message, code="invalid_status_transition", status_code=409)


class InvalidApplicationInputError(ApplicationError):
    def __init__(self, message: str):
        super().__init__(message, code="invalid_application_input", status_code=422)
