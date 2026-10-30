from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["demo", "live"]


class WebSearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResult(BaseModel):
    source: Source
    query: str
    results: list[WebSearchResultItem]


class JobListing(BaseModel):
    title: str
    company: str
    location: str | None = None
    remote: bool | None = None
    url: str
    posted_at: str | None = None
    summary: str | None = None


class SearchJobsResult(BaseModel):
    source: Source
    role: str
    results: list[JobListing]


class TechnologyRequirement(BaseModel):
    technology: str
    frequency_percent: float = Field(description="Share of sampled postings/listings mentioning this technology")
    importance: Literal["required", "preferred", "nice_to_have"]


class SearchTechnologyRequirementsResult(BaseModel):
    source: Source
    role: str
    technology_filter: str | None = None
    requirements: list[TechnologyRequirement]
