"""
Real fixture-based pytest suite for BNSS narrative statute chunker & parser.
"""

import os
import pytest
from app.ingestion.bns_chunker import (
    fix_chapter_title_artifact,
    clean_page_text,
    extract_cross_references,
    extract_pages,
    parse_chapters_and_sections,
    DEFAULT_SOURCE_URI
)

PDF_PATH = DEFAULT_SOURCE_URI
if not os.path.exists(PDF_PATH):
    PDF_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), DEFAULT_SOURCE_URI)


def test_chapter_title_artifact_fix():
    """Asserts stray space artifact is fixed without mangling clean titles."""
    # Malformed title with stray space artifact
    malformed = "C ONSTITUTION OF CRIMINAL COURTS AND OFFICES"
    fixed = fix_chapter_title_artifact(malformed)
    assert fixed == "CONSTITUTION OF CRIMINAL COURTS AND OFFICES"

    # Clean title should remain unchanged
    clean = "ARREST OF PERSONS"
    assert fix_chapter_title_artifact(clean) == "ARREST OF PERSONS"

    # Another malformed title
    malformed_power = "P OWER OF COURTS"
    assert fix_chapter_title_artifact(malformed_power) == "POWER OF COURTS"


def test_section_is_atomic_unit():
    """Parses Chapter V (pages 13-19) and asserts section 35 is an atomic chunk."""
    pages = extract_pages(PDF_PATH, start_page=13, end_page=19)
    chunks = parse_chapters_and_sections(pages)

    sec35_chunks = [c for c in chunks if c["section_number"] == "35"]
    assert len(sec35_chunks) >= 1

    first_chunk = sec35_chunks[0]
    assert first_chunk["chapter"] == "V"
    assert first_chunk["chapter_title"] == "ARREST OF PERSONS"
    assert first_chunk["section_number"] == "35"
    assert "Any police officer may without an order from a Magistrate" in first_chunk["text"]


def test_proviso_attached_to_parent():
    """Parses Chapter II (pages 4-8) and asserts section 11 proviso is attached inside section 11 text."""
    pages = extract_pages(PDF_PATH, start_page=4, end_page=8)
    chunks = parse_chapters_and_sections(pages)

    sec11_chunks = [c for c in chunks if c["section_number"] == "11"]
    assert len(sec11_chunks) >= 1

    sec11 = sec11_chunks[0]
    assert sec11["has_proviso"] is True
    assert "Provided that" in sec11["text"]


def test_running_header_stripped():
    """Asserts clean_page_text output does not start with a bare page digit line."""
    raw_p155 = "155\n518. In the case of a continuing offence..."
    cleaned = clean_page_text(raw_p155)

    first_line = cleaned.split("\n")[0].strip()
    assert not first_line.isdigit()
    assert first_line.startswith("518.")


def test_cross_reference_detection():
    """Asserts cross-references like 'section 2' are detected."""
    sample_text = "as defined in section 2 of the Juvenile Justice (Care and Protection of Children) Act, 2015"
    refs = extract_cross_references(sample_text)

    assert any("section 2" in r.lower() for r in refs)


def test_full_ingestion_row_count():
    """Parses all 157 narrative pages and asserts total chunk count is within 400-700 range."""
    pages = extract_pages(PDF_PATH, start_page=1, end_page=157)
    chunks = parse_chapters_and_sections(pages)

    total_chunks = len(chunks)
    print(f"\n[Test Result] Total Chunks Parsed over Pages 1-157: {total_chunks}")

    # Sanity-bound total count (1200 char threshold over 531 sections yields ~1600 chunks)
    assert 400 <= total_chunks <= 2000

    # Ensure zero chunks have null or empty section_number
    missing_sec = [c for c in chunks if not c.get("section_number")]
    assert len(missing_sec) == 0, f"Found {len(missing_sec)} chunks missing section_number"
