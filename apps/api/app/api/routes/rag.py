from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.rag.embeddings.factory import get_embedding_provider
from app.rag.errors import RAGError
from app.rag.service import RAGService
from app.schemas.rag import IngestRequest, IngestResponse, SearchRequest, SearchResponse, SearchResultItem
from app.security.deps import require_admin

router = APIRouter()


def _build_service(db: Session, request: Request) -> RAGService:
    vector_store = getattr(request.app.state, "vector_store", None)
    if vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store is not initialized")
    try:
        embedding_provider = get_embedding_provider()
    except RAGError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc
    return RAGService(db=db, vector_store=vector_store, embedding_provider=embedding_provider, settings=get_settings())


@router.post("/rag/ingest", response_model=IngestResponse, dependencies=[Depends(require_admin)])
async def ingest(payload: IngestRequest, request: Request, db: Session = Depends(get_db)) -> IngestResponse:
    service = _build_service(db, request)
    try:
        result = await service.ingest_document(
            title=payload.title,
            content=payload.content,
            source=payload.source,
            content_type=payload.document_type,
            extra_metadata=payload.metadata,
        )
    except RAGError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return IngestResponse(
        document_id=result.document_id,
        chunks_created=result.chunks_created,
        chunks_repaired=result.chunks_repaired,
        reingested=result.reingested,
    )


@router.post("/rag/search", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request, db: Session = Depends(get_db)) -> SearchResponse:
    service = _build_service(db, request)
    try:
        chunks, context = await service.search(payload.query, payload.top_k, payload.filters or None)
    except RAGError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return SearchResponse(
        results=[
            SearchResultItem(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                content=c.content,
                score=c.score,
                source=c.source,
                title=c.title,
                heading_path=c.heading_path,
            )
            for c in chunks
        ],
        context=context.text,
        sources=[
            {
                "document_id": s.document_id,
                "chunk_id": s.chunk_id,
                "title": s.title,
                "source": s.source,
                "heading_path": s.heading_path,
                "score": s.score,
            }
            for s in context.sources
        ],
    )
