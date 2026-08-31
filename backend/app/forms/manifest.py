"""
Manifest generator and database synchronization for statutory forms.
Writes data/forms/forms_manifest.json and updates PostgreSQL statutory_form rows.
"""

import os
import json
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.models import StatutoryForm
from app.core.logging import logger


def generate_manifest(
    forms_data: List[Dict[str, Any]],
    output_json_path: str = "data/forms/forms_manifest.json"
) -> List[Dict[str, Any]]:
    """
    Generates and saves forms_manifest.json containing metadata and verification hashes
    for all extracted statutory forms.
    """
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)

    manifest_records = []
    for f in forms_data:
        manifest_records.append({
            "form_number": f["form_number"],
            "title": f["title"],
            "enabling_section": f.get("enabling_section"),
            "page_start": f["page_start"],
            "page_end": f["page_end"],
            "filename": f["filename"],
            "byte_size": f["byte_size"],
            "sha256": f["sha256"],
            "extraction_confidence": f["extraction_confidence"],
            "needs_review": f.get("needs_review", False)
        })

    manifest_records.sort(key=lambda x: x["form_number"])

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_records, f, indent=2, ensure_ascii=False)

    logger.info("Successfully wrote forms manifest with %d entries to '%s'.", len(manifest_records), output_json_path)
    return manifest_records


async def sync_forms_to_db(
    session: AsyncSession,
    forms_data: List[Dict[str, Any]]
) -> int:
    """
    Synchronizes extracted statutory forms metadata with PostgreSQL statutory_form table.
    Idempotent: updates existing rows by form_number or inserts new ones.
    
    Returns:
        Number of synchronized records.
    """
    logger.info("Syncing %d statutory forms to PostgreSQL...", len(forms_data))

    # Fetch existing form records
    stmt = select(StatutoryForm)
    result = await session.execute(stmt)
    existing_by_num = {f.form_number: f for f in result.scalars().all()}

    synced_count = 0
    for f in forms_data:
        form_num = f["form_number"]
        if form_num in existing_by_num:
            # Update existing
            row = existing_by_num[form_num]
            row.title = f["title"]
            row.enabling_section = f.get("enabling_section")
            row.page_start = f["page_start"]
            row.page_end = f["page_end"]
            row.filename = f["filename"]
            row.byte_size = f["byte_size"]
            row.sha256 = f["sha256"]
            row.extraction_confidence = f["extraction_confidence"]
            row.needs_review = f.get("needs_review", False)
        else:
            # Insert new
            row = StatutoryForm(
                form_number=form_num,
                title=f["title"],
                enabling_section=f.get("enabling_section"),
                page_start=f["page_start"],
                page_end=f["page_end"],
                filename=f["filename"],
                byte_size=f["byte_size"],
                sha256=f["sha256"],
                extraction_confidence=f["extraction_confidence"],
                needs_review=f.get("needs_review", False)
            )
            session.add(row)
        synced_count += 1

    await session.commit()
    logger.info("Successfully committed %d statutory form rows to PostgreSQL statutory_form table.", synced_count)
    return synced_count
