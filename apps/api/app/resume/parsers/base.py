from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedResumeText:
    text: str
    warnings: list[str] = field(default_factory=list)


class ResumeParser(ABC):
    @abstractmethod
    def parse(self, raw: bytes) -> ParsedResumeText: ...
