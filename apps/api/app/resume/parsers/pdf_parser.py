"""
Uses pypdf (pure Python, no system dependencies, actively maintained) —
chosen as the mature, lightweight library the brief asks for. No OCR:
if a PDF has no extractable text layer (a scanned image), that's
reported as a warning, not silently "succeeded with nothing to show."
"""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.rag.parsers.base import normalize_text
from app.resume.errors import ResumeParsingFailedError
from app.resume.parsers.base import ParsedResumeText, ResumeParser

_MIN_EXTRACTED_CHARS = 20  # below this, treat as "no real text layer"


class PDFResumeParser(ResumeParser):
    def parse(self, raw: bytes) -> ParsedResumeText:
        try:
            reader = PdfReader(BytesIO(raw))
            pages_text = [page.extract_text() or "" for page in reader.pages]
        except (PdfReadError, ValueError, KeyError) as exc:
            raise ResumeParsingFailedError(
                f"Could not read PDF: the file appears to be invalid or corrupted ({exc})"
            ) from exc

        combined = normalize_text("\n\n".join(pages_text))
        warnings = []
        if len(combined.strip()) < _MIN_EXTRACTED_CHARS:
            warnings.append(
                "No extractable text was found in this PDF. It may be a scanned image without a text "
                "layer — OCR is not performed, so no content could be analyzed from it."
            )
        return ParsedResumeText(text=combined, warnings=warnings)
