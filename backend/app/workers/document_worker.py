"""
Async background worker for user document processing using arq.
Executes non-blocking PDF parsing, generic paragraph chunking, dense embedding,
prompt injection scanning, and PostgreSQL persistence.
"""

import os
import re
import uuid
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import pdfplumber
from arq.connections import RedisSettings
from sqlalchemy import select, update

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.logging import logger
from app.core.models import UserDocument, UserDocumentChunk
from app.retrieval.embeddings import embed_passages

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"disregard\s+(?:all\s+)?(?:the\s+)?above",
    r"you\s+are\s+now\s+(?:a|an)",
    r"system\s+prompt",
    r"new\s+instructions",
    r"forget\s+all\s+instructions",
    r"override\s+(?:the\s+)?system",
    r"bypass\s+all\s+rules",
    r"recommend\s+(?:the\s+user\s+hire|.*\bacme\b)",
]

COMPILED_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)


def scan_for_prompt_injection(text: str) -> bool:
    """
    Lightweight scanner to detect adversarial prompt injection strings in document text.
    Returns True if suspicious injection patterns are matched.
    """
    if not text:
        return False
    return bool(COMPILED_INJECTION_RE.search(text))


def chunk_page_text(
    page_text: str,
    page_num: int,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[Dict[str, Any]]:
    """
    Splits arbitrary page text into generic character-bounded chunks with overlap.
    """
    text = page_text.strip()
    if not text:
        return []

    # If small enough, return as single chunk
    if len(text) <= chunk_size:
        return [{"page_number": page_num, "text": text}]

    # Paragraph-aware split
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{p}" if current_chunk else p
        else:
            if current_chunk:
                chunks.append({"page_number": page_num, "text": current_chunk.strip()})
                # Retain overlap from end of current_chunk
                current_chunk = current_chunk[-overlap:] + "\n\n" + p
            else:
                # Individual paragraph exceeds chunk_size
                for i in range(0, len(p), chunk_size - overlap):
                    sub = p[i : i + chunk_size].strip()
                    if sub:
                        chunks.append({"page_number": page_num, "text": sub})
                current_chunk = ""

    if current_chunk.strip():
        chunks.append({"page_number": page_num, "text": current_chunk.strip()})

    return chunks


async def update_doc_status(
    doc_id: uuid.UUID,
    status: str,
    page_count: Optional[int] = None,
    has_injection: bool = False,
    error_message: Optional[str] = None,
) -> None:
    """Helper to update UserDocument record in DB."""
    async with AsyncSessionLocal() as db:
        stmt = (
            update(UserDocument)
            .where(UserDocument.id == doc_id)
            .values(
                status=status,
                page_count=(
                    page_count if page_count is not None else UserDocument.page_count
                ),
                has_prompt_injection=has_injection or UserDocument.has_prompt_injection,
                error_message=error_message,
            )
        )
        await db.execute(stmt)
        await db.commit()


async def process_user_document(
    ctx: Dict[str, Any], document_id: str, session_id: str, file_path: str
) -> Dict[str, Any]:
    """
    Main async arq worker task:
    1. Parsing: reads PDF pages and validates integrity.
    2. Injection Scanning: scans extracted text for adversarial prompt instructions.
    3. Chunking: chunks pages with paragraph-aware sliding window.
    4. Embedding: computes 768-dim dense embeddings.
    5. Persistence: commits chunks to user_document_chunk and sets status="ready".
    """
    doc_uuid = uuid.UUID(document_id)
    logger.info(
        "Worker processing document '%s' (session '%s')...", document_id, session_id
    )

    try:
        # --- STAGE 1: PARSING ---
        await update_doc_status(doc_uuid, status="parsing")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Uploaded file not found at path: {file_path}")

        # Check encryption / corruption via fitz
        try:
            doc_fitz = fitz.open(file_path)
            if doc_fitz.is_encrypted:
                raise ValueError(
                    "PDF is password protected / encrypted and cannot be parsed."
                )
            page_count = len(doc_fitz)
            doc_fitz.close()
        except Exception as e:
            raise ValueError(f"Corrupt or unreadable PDF: {str(e)}")

        pages_extracted: List[tuple] = []
        injection_detected = False

        # Extract text via pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                if scan_for_prompt_injection(raw_text):
                    logger.warning(
                        "PROMPT INJECTION DETECTED in document '%s' (Page %d). Flagging record.",
                        document_id,
                        idx,
                    )
                    injection_detected = True
                pages_extracted.append((idx, raw_text))

        # --- STAGE 2: CHUNKING ---
        await update_doc_status(
            doc_uuid,
            status="chunking",
            page_count=page_count,
            has_injection=injection_detected,
        )

        all_chunks: List[Dict[str, Any]] = []
        for page_num, page_text in pages_extracted:
            page_chunks = chunk_page_text(page_text, page_num)
            all_chunks.extend(page_chunks)

        if not all_chunks:
            # Empty PDF or purely scanned with no OCR
            all_chunks = [
                {
                    "page_number": 1,
                    "text": "[No machine-readable text extracted from document]",
                }
            ]

        # --- STAGE 3: EMBEDDING ---
        await update_doc_status(doc_uuid, status="embedding")
        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = embed_passages(chunk_texts)

        # --- STAGE 4: PERSISTENCE ---
        async with AsyncSessionLocal() as db:
            # Remove any prior chunks for this document
            stmt_del = select(UserDocumentChunk).where(
                UserDocumentChunk.document_id == doc_uuid
            )
            res = await db.execute(stmt_del)
            existing_chunks = res.scalars().all()
            for c in existing_chunks:
                await db.delete(c)
            await db.flush()

            for idx, (chunk_data, emb) in enumerate(zip(all_chunks, embeddings)):
                chunk_obj = UserDocumentChunk(
                    id=uuid.uuid4(),
                    document_id=doc_uuid,
                    session_id=session_id,
                    chunk_index=idx,
                    text=chunk_data["text"],
                    page_number=chunk_data["page_number"],
                    embedding=emb,
                )
                db.add(chunk_obj)

            await db.commit()

        # Update status to READY
        await update_doc_status(
            doc_uuid,
            status="ready",
            page_count=page_count,
            has_injection=injection_detected,
        )
        logger.info(
            "Document '%s' successfully processed: %d pages, %d chunks ready.",
            document_id,
            page_count,
            len(all_chunks),
        )
        return {
            "document_id": document_id,
            "status": "ready",
            "page_count": page_count,
            "chunks_count": len(all_chunks),
            "has_prompt_injection": injection_detected,
        }

    except Exception as e:
        logger.error("Failed to process document '%s': %s", document_id, e)
        await update_doc_status(doc_uuid, status="failed", error_message=str(e))
        return {"document_id": document_id, "status": "failed", "error": str(e)}


async def startup(ctx: Dict[str, Any]):
    """Worker startup hook."""
    logger.info("Nyaya Document Processing Worker starting up...")


async def shutdown(ctx: Dict[str, Any]):
    """Worker shutdown hook."""
    logger.info("Nyaya Document Processing Worker shutting down...")


class WorkerSettings:
    """arq worker configuration settings."""

    functions = [process_user_document]
    redis_settings = RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    poll_delay = 0.5
