from app.rag.parsers.base import normalize_text
from app.resume.parsers.base import ParsedResumeText, ResumeParser


class TextResumeParser(ResumeParser):
    def parse(self, raw: bytes) -> ParsedResumeText:
        warnings = []
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            warnings.append("Resume text contained non-UTF-8 bytes; some characters may have been replaced.")
        return ParsedResumeText(text=normalize_text(text), warnings=warnings)
