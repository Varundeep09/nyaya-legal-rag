"""
Document management endpoints for Nyaya Legal Assistant.
Provides session-isolated document upload, status polling, listing,
and cascade deletion.
"""

import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import fitz  # PyMuPDF
from arq.connections import RedisSettings, create_pool

from app.core.config import settings
from app.core.db import get_db
from app.core.logging import logger
from app.core.models import UserDocument, UserDocumentChunk
from app.core.session import get_session_id_from_header, ensure_session_exists
from app.workers.document_worker import process_user_document

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB
UPLOAD_BASE_DIR = os.path.join("data", "uploads")


class DocumentUploadResponse(BaseModel):
    document_id: str
    job_id: str
    filename: str
    status: str
    session_id: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: Optional[int] = None
    chunks_ready: int = 0
    has_prompt_injection: bool = False
    error_message: Optional[str] = None


class DocumentListItem(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: Optional[int] = None
    created_at: str


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Depends(get_session_id_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a user PDF document for session-isolated background ingestion.
    Validates MIME magic bytes, size limits, and encryption.
    """
    logger.info("Received document upload request for session '%s', filename: '%s'", session_id, file.filename)

    # 1. Read file content
    content = await file.read()
    file_size = len(content)

    # 2. Size limit validation
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of 20MB (received {file_size / (1024*1024):.2f}MB)."
        )

    # 3. MIME magic bytes sniffing
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Uploaded file is not a valid PDF document (missing %PDF- header)."
        )

    # 4. Integrity and encryption validation via PyMuPDF
    try:
        doc_fitz = fitz.open(stream=content, filetype="pdf")
        if doc_fitz.is_encrypted:
            doc_fitz.close()
            raise HTTPException(
                status_code=400,
                detail="Encrypted or password-protected PDFs are not supported. Please upload an unprotected PDF."
            )
        if len(doc_fitz) == 0:
            doc_fitz.close()
            raise HTTPException(status_code=400, detail="Corrupted PDF with 0 pages.")
        doc_fitz.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("PDF integrity check failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail=f"Corrupted or malformed PDF file: {str(e)}"
        )

    # 5. Persist file to session storage
    session_upload_dir = os.path.join(UPLOAD_BASE_DIR, session_id)
    os.makedirs(session_upload_dir, exist_ok=True)

    doc_uuid = uuid.uuid4()
    saved_filename = f"{doc_uuid}.pdf"
    file_path = os.path.join(session_upload_dir, saved_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    # 6. Ensure ChatSession exists and create UserDocument record
    await ensure_session_exists(session_id, db)

    user_doc = UserDocument(
        id=doc_uuid,
        session_id=session_id,
        filename=file.filename or "uploaded_document.pdf",
        status="uploaded"
    )
    db.add(user_doc)
    await db.commit()

    # 7. Enqueue arq background job (or execute directly if redis is connecting)
    job_id = f"job-{doc_uuid}"
    try:
        redis_pool = await create_pool(
            RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        )
        job = await redis_pool.enqueue_job(
            "process_user_document",
            str(doc_uuid),
            session_id,
            file_path,
            _job_id=job_id
        )
        if job:
            job_id = job.job_id
        await redis_pool.close()
    except Exception as e:
        logger.warning(
            "Failed to enqueue arq job via Redis (%s). Processing document synchronously as fallback...",
            e
        )
        # Fallback to direct background execution for local standalone environments
        import asyncio
        asyncio.create_task(process_user_document({}, str(doc_uuid), session_id, file_path))

    logger.info("Enqueued document processing job '%s' for document '%s'", job_id, doc_uuid)
    return DocumentUploadResponse(
        document_id=str(doc_uuid),
        job_id=job_id,
        filename=user_doc.filename,
        status="uploaded",
        session_id=session_id
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    session_id: str = Depends(get_session_id_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Checks the async processing status of a document.
    Enforces strict session ownership — returns 404 if document belongs to another session.
    """
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document UUID format.")

    stmt = (
        select(UserDocument)
        .where(UserDocument.id == doc_uuid)
    )
    res = await db.execute(stmt)
    user_doc = res.scalar_one_or_none()

    # Ownership check
    if not user_doc or user_doc.session_id != session_id:
        logger.warning(
            "Access denied to document '%s' (session '%s' requested, doc belongs to '%s')",
            document_id, session_id, user_doc.session_id if user_doc else "None"
        )
        raise HTTPException(status_code=404, detail="Document not found.")

    # Count ready chunks
    stmt_chunks = (
        select(func.count(UserDocumentChunk.id))
        .where(UserDocumentChunk.document_id == doc_uuid)
    )
    res_chunks = await db.execute(stmt_chunks)
    chunks_ready = res_chunks.scalar() or 0

    return DocumentStatusResponse(
        document_id=str(user_doc.id),
        filename=user_doc.filename,
        status=user_doc.status,
        page_count=user_doc.page_count,
        chunks_ready=chunks_ready,
        has_prompt_injection=user_doc.has_prompt_injection,
        error_message=user_doc.error_message
    )


@router.get("", response_model=List[DocumentListItem])
async def list_user_documents(
    session_id: str = Depends(get_session_id_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists all uploaded documents for the current session only.
    """
    stmt = (
        select(UserDocument)
        .where(UserDocument.session_id == session_id)
        .order_by(UserDocument.created_at.desc())
    )
    res = await db.execute(stmt)
    docs = res.scalars().all()

    return [
        DocumentListItem(
            document_id=str(d.id),
            filename=d.filename,
            status=d.status,
            page_count=d.page_count,
            created_at=d.created_at.isoformat() if d.created_at else ""
        )
        for d in docs
    ]


@router.delete("/{document_id}")
async def delete_user_document(
    document_id: str,
    session_id: str = Depends(get_session_id_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes a user document and its embedded chunks.
    Enforces strict session ownership — returns 404 if document belongs to another session.
    """
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document UUID format.")

    stmt = select(UserDocument).where(UserDocument.id == doc_uuid)
    res = await db.execute(stmt)
    user_doc = res.scalar_one_or_none()

    # Ownership check
    if not user_doc or user_doc.session_id != session_id:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Delete parent document (foreign key cascades to user_document_chunk)
    await db.delete(user_doc)
    await db.commit()

    # Remove stored physical file if present
    session_upload_dir = os.path.join(UPLOAD_BASE_DIR, session_id)
    file_path = os.path.join(session_upload_dir, f"{doc_uuid}.pdf")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning("Failed to remove local upload file '%s': %s", file_path, e)

    logger.info("Successfully deleted document '%s' and cascaded chunks for session '%s'", document_id, session_id)
    return {"message": "Document deleted successfully", "document_id": document_id}
