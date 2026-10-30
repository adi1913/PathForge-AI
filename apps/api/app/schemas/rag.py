from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source: str | None = None
    document_type: str = Field(default="text", description="'text' or 'markdown'")
    metadata: dict = Field(default_factory=dict, description="Filterable fields, e.g. skill/difficulty/resource_type")


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    chunks_repaired: int
    reingested: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = 5
    filters: dict = Field(default_factory=dict)


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    source: str | None
    title: str | None
    heading_path: list[str]


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    context: str
    sources: list[dict]
