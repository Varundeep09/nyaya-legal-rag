"""
Statutory Form Extraction Pipeline for The Second Schedule (pages 190-249).
Extracts all 58 statutory forms, detects boundaries, scrapes titles dynamically
(zero hardcoding), parses enabling sections, and exports page-perfect vector PDFs.
"""

import hashlib
import os
import re
import unicodedata
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pdfplumber

from app.core.logging import logger


def slugify(text: str) -> str:
    """
    Converts a title string to a clean, deterministic, filesystem-safe slug.
    Lowercase, spaces/punctuation converted to single hyphens.
    """
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def clean_enabling_section(raw_line: str) -> str:
    """
    Extracts the statutory section cross-reference from lines such as:
    - '[See section 35(3)]' -> '35(3)'
    - '(See sections 234, 235 and 236)' -> '234, 235 and 236'
    - '[See sections 478, 479, 480, 481, 482(3) and 485]' -> '478, 479, 480, 481, 482(3) and 485'
    """
    raw = raw_line.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    elif raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    elif raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.rfind("]")].strip()
    elif raw.startswith("(") and ")" in raw:
        raw = raw[1 : raw.rfind(")")].strip()

    m = re.search(r"See\s+sections?\s+(.*)", raw, re.IGNORECASE)
    if m:
        sec = m.group(1).strip()
        sec = re.sub(r"\s+", " ", sec)
        return sec
    return ""


def detect_form_boundaries(
    pdf_path: str, start_page: int = 190, end_page: int = 249
) -> List[Dict[str, Any]]:
    """
    Detects all 58 statutory form boundaries in pages start_page..end_page of the PDF.
    Scrapes the title dynamically from the all-caps line following 'FORM No.<N>'.

    Zero hardcoded title dictionaries are used.

    Returns:
        List of dicts with: form_number, title, enabling_section, page_start, page_end,
        extraction_confidence, needs_review.
    """
    logger.info(
        "Scanning PDF '%s' for statutory forms between pages %d and %d...",
        pdf_path,
        start_page,
        end_page,
    )
    form_header_re = re.compile(r"^FORM\s+No\.?\s*(\d+)", re.IGNORECASE)

    raw_forms = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        actual_end = min(end_page, total_pages)

        for page_idx in range(start_page - 1, actual_end):
            page = pdf.pages[page_idx]
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            page_num = page_idx + 1

            # OCR / text quality check
            words = text.split()
            if len(words) < 10:
                logger.warning(
                    "Page %d has sparse text (%d words). May require OCR fallback.",
                    page_num,
                    len(words),
                )

            for i, line in enumerate(lines):
                m = form_header_re.match(line)
                if m:
                    form_num = int(m.group(1))
                    title_lines = []
                    enabling_sec = ""

                    # Inspect the lines immediately following the form header
                    for j in range(i + 1, min(i + 8, len(lines))):
                        cand = lines[j]
                        if re.search(r"[\[\(]\s*See\s+sections?", cand, re.IGNORECASE):
                            enabling_sec = clean_enabling_section(cand)
                            break
                        # Detect all-caps title lines
                        if cand.isupper() or (
                            len(cand) > 3
                            and sum(1 for c in cand if c.isupper()) / max(len(cand), 1)
                            > 0.5
                        ):
                            title_lines.append(cand)
                        elif not title_lines:
                            title_lines.append(cand)

                    scraped_title = " ".join(title_lines).strip()
                    scraped_title = re.sub(r"\s+", " ", scraped_title)

                    # Assess confidence
                    confidence = 1.0
                    needs_review = False
                    if not scraped_title or len(scraped_title) < 3:
                        confidence = 0.5
                        needs_review = True
                        scraped_title = f"FORM {form_num}"
                    elif not enabling_sec:
                        confidence = 0.85

                    raw_forms.append(
                        {
                            "form_number": form_num,
                            "title": scraped_title,
                            "enabling_section": enabling_sec or None,
                            "page_start": page_num,
                            "line_idx": i,
                            "extraction_confidence": round(confidence, 2),
                            "needs_review": needs_review,
                        }
                    )

    # Sort forms sequentially by form_number
    raw_forms.sort(key=lambda x: (x["form_number"], x["page_start"]))

    # Deduplicate in case of multiple detections
    unique_forms: List[Dict[str, Any]] = []
    seen_nums = set()
    for f in raw_forms:
        if f["form_number"] not in seen_nums:
            unique_forms.append(f)
            seen_nums.add(f["form_number"])

    # Calculate page_end for each form
    for k in range(len(unique_forms)):
        current = unique_forms[k]
        if k < len(unique_forms) - 1:
            next_form = unique_forms[k + 1]
            if next_form["page_start"] > current["page_start"]:
                current["page_end"] = next_form["page_start"] - 1
            else:
                current["page_end"] = current["page_start"]
        else:
            current["page_end"] = end_page

    logger.info(
        "Successfully detected %d statutory forms across pages %d-%d.",
        len(unique_forms),
        start_page,
        end_page,
    )
    return unique_forms


def extract_form_pdf(
    source_pdf_path: str,
    page_start: int,
    page_end: int,
    output_path: str,
    force_overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Extracts a page-perfect vector PDF from source_pdf_path for page_start..page_end.
    Computes byte size and SHA-256 hash.
    Idempotent: if output file already exists and force_overwrite is False, reuses existing file bytes.

    Returns:
        Dict with filename, byte_size, sha256.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not os.path.exists(output_path) or force_overwrite:
        src_doc = fitz.open(source_pdf_path)
        out_doc = fitz.open()

        # PyMuPDF uses 0-indexed page numbers
        out_doc.insert_pdf(src_doc, from_page=page_start - 1, to_page=page_end - 1)
        out_doc.save(output_path, deflate=True, clean=True)
        out_doc.close()
        src_doc.close()

    with open(output_path, "rb") as f:
        file_bytes = f.read()

    byte_size = len(file_bytes)
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    return {
        "filename": os.path.basename(output_path),
        "byte_size": byte_size,
        "sha256": sha256_hash,
    }
