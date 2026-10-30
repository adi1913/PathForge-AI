class RepoEvalError(Exception):
    """All messages are fixed strings: upstream text and tokens are never echoed."""

    def __init__(self, message: str, *, code: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class InvalidRepositoryUrlError(RepoEvalError):
    def __init__(self):
        super().__init__(
            "repository_url must be https://github.com/<owner>/<repo> or <owner>/<repo>",
            code="invalid_repository_url",
            status_code=422,
        )


class RepositoryNotFoundError(RepoEvalError):
    def __init__(self):
        super().__init__(
            "Repository not found or not public. Only public GitHub repositories can be evaluated.",
            code="repository_not_found",
            status_code=404,
        )


class GitHubRateLimitedError(RepoEvalError):
    def __init__(self):
        super().__init__(
            "GitHub rate limit reached. Try again later (a GITHUB_TOKEN on the server raises the limit).",
            code="github_rate_limited",
            status_code=429,
        )


class GitHubUnavailableError(RepoEvalError):
    def __init__(self, message: str = "GitHub could not be reached or returned unusable data."):
        super().__init__(message, code="github_unavailable", status_code=502)


class GitHubMCPUnavailableError(RepoEvalError):
    def __init__(self):
        super().__init__("The GitHub MCP server is not available.", code="github_mcp_unavailable", status_code=503)


class EvaluationNotFoundError(RepoEvalError):
    """Also raised for another user's evaluation, so existence is never leaked."""

    def __init__(self):
        super().__init__("Evaluation not found", code="evaluation_not_found", status_code=404)


class UserNotFoundError(RepoEvalError):
    def __init__(self):
        super().__init__("User not found", code="user_not_found", status_code=404)
