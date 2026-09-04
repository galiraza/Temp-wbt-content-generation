"""Parses the Meta Ads Content docx into example chunks and upserts them into
Pinecone. Run via scripts/ingest_rag.py whenever the docx changes — not on
every server startup.
"""

from pathlib import Path
from typing import List, Optional

import docx
from docx.oxml.ns import qn

from app.rag.clients import embed_texts, get_pinecone_index

DOCX_PATH = Path(__file__).parent.parent.parent / "data" / "meta_ads_examples.docx"


def parse_docx_examples(path: Path = DOCX_PATH) -> List[dict]:
    """Walks the docx body in document order. Top-level paragraphs (that aren't
    "Content N:" labels) are treated as industry section headers; each table
    that follows is one client's set of example angles for that industry.

    Returns a flat list of {industry, source_label, headline, primary_text}.
    """
    document = docx.Document(str(path))
    body = document.element.body

    chunks: List[dict] = []
    current_industry: Optional[str] = None
    content_index = 0

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]

        if tag == "p":
            text = "".join(node.text or "" for node in child.iter(qn("w:t"))).strip()
            if not text:
                continue
            if text.lower().startswith("content"):
                continue
            # A new top-level heading — reset to a new industry section.
            current_industry = text
            content_index = 0

        elif tag == "tbl":
            if current_industry is None:
                continue
            content_index += 1
            source_label = f"{current_industry} / Content {content_index}"

            table = docx.table.Table(child, document)
            rows = table.rows
            if not rows:
                continue

            header_cells = [c.text.strip().upper() for c in rows[0].cells]
            try:
                headline_col = header_cells.index("HEADLINE")
                primary_col = header_cells.index("PRIMARY TEXT")
            except ValueError:
                continue

            seen_rows = set()
            for row in rows[1:]:
                cells = row.cells
                if len(cells) <= max(headline_col, primary_col):
                    continue
                headline = cells[headline_col].text.strip()
                primary_text = cells[primary_col].text.strip()
                if not headline or not primary_text:
                    continue
                dedupe_key = (headline, primary_text)
                if dedupe_key in seen_rows:
                    continue
                seen_rows.add(dedupe_key)
                chunks.append(
                    {
                        "industry": current_industry,
                        "source_label": source_label,
                        "headline": headline,
                        "primary_text": primary_text,
                    }
                )

    return chunks


def build_index(path: Path = DOCX_PATH, batch_size: int = 100) -> int:
    """One-time/idempotent ingestion: parses the docx and upserts every example
    chunk into Pinecone. Returns the number of chunks upserted. Safe to re-run —
    IDs are deterministic, so re-running just overwrites the same vectors.
    """
    index = get_pinecone_index()
    if index is None:
        raise RuntimeError("PINECONE_API_KEY / PINECONE_INDEX_NAME are not set.")

    chunks = parse_docx_examples(path)

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        texts = [f"{c['industry']}\n{c['headline']}\n{c['primary_text']}" for c in batch]
        embeddings = embed_texts(texts)

        vectors = []
        for i, (chunk, embedding) in enumerate(zip(batch, embeddings)):
            vectors.append(
                {
                    "id": f"chunk-{batch_start + i}",
                    "values": embedding,
                    "metadata": {
                        "industry": chunk["industry"],
                        "source_label": chunk["source_label"],
                        "headline": chunk["headline"],
                        "primary_text": chunk["primary_text"],
                    },
                }
            )
        index.upsert(vectors=vectors)

    return len(chunks)
