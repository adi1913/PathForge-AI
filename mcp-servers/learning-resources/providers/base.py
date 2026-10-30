import sys
from abc import ABC, abstractmethod
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import Difficulty, GetLearningResourceResult, ResourceType, SearchLearningResourcesResult


class LearningResourceProvider(ABC):
    """Backs all four learning-resource tools. `search_courses` and
    `search_documentation` (in server.py) are thin wrappers over
    `search_resources` with `resource_type` pinned — one provider method
    covers all three search-shaped tools, so demo/real implementations
    don't duplicate filtering logic three times."""

    @abstractmethod
    async def search_resources(
        self,
        query: str | None,
        skill: str | None,
        level: Difficulty | None,
        resource_type: ResourceType | None,
        max_results: int,
    ) -> SearchLearningResourcesResult: ...

    @abstractmethod
    async def get_resource(self, resource_id: str) -> GetLearningResourceResult: ...
