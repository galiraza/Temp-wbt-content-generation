"""One-off ingestion script: parses the Meta Ads Content docx and upserts every
example chunk into the Pinecone index. Run manually whenever the docx changes:

    python scripts/ingest_rag.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.ingestion import build_index  # noqa: E402

if __name__ == "__main__":
    count = build_index()
    print(f"Upserted {count} example chunks into Pinecone.")
