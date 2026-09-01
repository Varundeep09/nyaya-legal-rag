"""
API endpoints for querying, previewing, and downloading Statutory Forms (Second Schedule).
"""

import os
import io
import zipfile
import uuid
from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import logger
from app.core.models import StatutoryForm

router = APIRouter(prefix="/forms", tags=["forms"])

FORMS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "forms")


class StatutoryFormOut(BaseModel):
    id: uuid.UUID
    form_number: int
    title: str
    enabling_section: Optional[str] = None
    page_start: int
    page_end: int
    filename: str
    byte_size: int
    sha256: str
    extraction_confidence: float
    needs_review: bool

    class Config:
        from_attributes = True



@router.get("", response_model=List[StatutoryFormOut])
async def list_statutory_forms(query: Optional[str] = None):
    """
    Returns all 58 statutory forms from The Second Schedule, optionally filtered by title or enabling section.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(StatutoryForm).order_by(StatutoryForm.form_number)
        result = await session.execute(stmt)
        forms = result.scalars().all()

        if query:
            q_lower = query.strip().lower()
            forms = [
                f for f in forms
                if q_lower in f.title.lower() or (f.enabling_section and q_lower in f.enabling_section.lower()) or q_lower in f.filename.lower()
            ]

        return forms


@router.get("/download-all")
async def download_all_forms_zip():
    """
    Creates and streams a zip archive containing all 58 statutory form PDFs.
    """
    if not os.path.exists(FORMS_DIR):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forms directory not found on disk."
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for fname in sorted(os.listdir(FORMS_DIR)):
            if fname.endswith(".pdf"):
                full_path = os.path.join(FORMS_DIR, fname)
                zip_file.write(full_path, arcname=fname)

    zip_buffer.seek(0)
    logger.info("Generated bulk forms zip archive with %d bytes.", len(zip_buffer.getvalue()))

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=BNSS_Statutory_Forms_1_to_58.zip"}
    )


@router.get("/{form_id}/download")
async def download_form_pdf(form_id: str):
    """
    Streams a single statutory form vector PDF file for download or in-browser preview.
    """
    async with AsyncSessionLocal() as session:
        # Allow looking up by UUID id or numeric form_number
        if form_id.isdigit():
            stmt = select(StatutoryForm).where(StatutoryForm.form_number == int(form_id))
        else:
            stmt = select(StatutoryForm).where(StatutoryForm.id == form_id)
        
        result = await session.execute(stmt)
        form_obj = result.scalar_one_or_none()

        if not form_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Statutory form '{form_id}' not found."
            )

        file_path = os.path.join(FORMS_DIR, form_obj.filename)
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Form PDF file '{form_obj.filename}' missing on disk."
            )

        return FileResponse(
            path=file_path,
            filename=form_obj.filename,
            media_type="application/pdf"
        )
