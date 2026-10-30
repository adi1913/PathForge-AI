"""Errors raised by the RAG pipeline. Kept separate from app/agent/errors.py
— the agent consumes RAG results (once wired in a later phase), it
doesn't raise these itself."""


class RAGError(Exception):
    def __init__(self, message: str, *, code: str = "rag_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentTooLargeError(RAGError):
    def __init__(self, message: str):
        super().__init__(message, code="document_too_large")


class UnsupportedContentTypeError(RAGError):
    def __init__(self, content_type: str):
        super().__init__(f"Unsupported document content_type: '{content_type}'", code="unsupported_content_type")


class EmbeddingUnavailableError(RAGError):
    """DEMO_MODE=false and no real embedding provider is configured."""

    def __init__(self, message: str):
        super().__init__(message, code="embedding_unavailable")


class EmbeddingProviderError(RAGError):
    def __init__(self, message: str):
        super().__init__(message, code="embedding_provider_error")


class VectorStoreError(RAGError):
    def __init__(self, message: str):
        super().__init__(message, code="vector_store_error")


class DocumentNotFoundError(RAGError):
    def __init__(self, document_id: str):
        super().__init__(f"Document '{document_id}' not found", code="document_not_found")
