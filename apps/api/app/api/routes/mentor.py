from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.agent.errors import AgentError
from app.agent.llm.factory import get_llm_provider
from app.core.config import get_settings
from app.db.session import get_db
from app.mentor.errors import MentorError
from app.mentor.schemas import MentorReply, MessageRequest, SessionCreate, SessionDetail, SessionOut
from app.mentor.service import MentorService
from app.rag.embeddings.factory import get_embedding_provider
from app.rag.errors import RAGError
from app.rag.service import RAGService

router = APIRouter()


def _service(db: Session, request: Request) -> MentorService:
    settings = get_settings()
    rag = None
    vector_store = getattr(request.app.state, "vector_store", None)
    if vector_store is not None:
        try:
            rag = RAGService(
                db=db, vector_store=vector_store, embedding_provider=get_embedding_provider(), settings=settings
            )
        except RAGError:  # the mentor degrades and discloses the missing knowledge base
            rag = None
    llm = None
    if not settings.DEMO_MODE:
        try:
            llm = get_llm_provider(settings)
        except (AgentError, NotImplementedError):
            llm = None
    return MentorService(db, settings, rag=rag, llm=llm)


def _fail(exc: MentorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/mentor/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, request: Request, db: Session = Depends(get_db)) -> SessionOut:
    try:
        return _service(db, request).create_session(payload)
    except MentorError as exc:
        raise _fail(exc) from exc


@router.get("/mentor/sessions", response_model=list[SessionOut])
def list_sessions(user_id: str, request: Request, db: Session = Depends(get_db)) -> list[SessionOut]:
    return _service(db, request).list_sessions(user_id)


@router.get("/mentor/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, user_id: str, request: Request, db: Session = Depends(get_db)) -> SessionDetail:
    try:
        return _service(db, request).get_session(session_id, user_id)
    except MentorError as exc:
        raise _fail(exc) from exc


@router.post("/mentor/sessions/{session_id}/messages", response_model=MentorReply)
async def post_message(
    session_id: str, payload: MessageRequest, request: Request, db: Session = Depends(get_db)
) -> MentorReply:
    try:
        return await _service(db, request).post_message(session_id, payload)
    except MentorError as exc:
        raise _fail(exc) from exc
