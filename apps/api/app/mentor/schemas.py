from datetime import datetime

from pydantic import BaseModel, Field

from app.assessments.schemas import AssessmentOut


class SessionCreate(BaseModel):
    user_id: str
    title: str | None = Field(default=None, max_length=255)


class SessionOut(BaseModel):
    id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict | None = None


class SessionDetail(SessionOut):
    messages: list[MessageOut]


class MessageRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=10_000)  # tightened by MENTOR_MAX_MESSAGE_CHARS in the service


class Citation(BaseModel):
    index: int
    title: str | None
    source: str | None
    heading: str | None
    document_id: str
    chunk_id: str
    score: float


class MentorAction(BaseModel):
    type: str
    assessment_id: str | None = None
    detail: str


class MentorReply(BaseModel):
    session_id: str
    user_message_id: str
    mentor_message_id: str
    intent: str
    answer: str
    answer_source: str  # demo_rules | llm
    citations: list[Citation]
    missing_context: list[str]
    actions: list[MentorAction]
    assessment: AssessmentOut | None = None  # key-free questions, when the mentor created one
