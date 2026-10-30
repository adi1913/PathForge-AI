from app.rag.parsers.base import DocumentParser, ParsedBlock, ParsedDocument, normalize_text


class PlainTextParser(DocumentParser):
    def parse(self, raw_content: str) -> ParsedDocument:
        text = normalize_text(raw_content)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        blocks = [ParsedBlock(kind="paragraph", text=p, heading_path=[]) for p in paragraphs]
        title = paragraphs[0][:100] if paragraphs else None
        return ParsedDocument(title=title, blocks=blocks)
