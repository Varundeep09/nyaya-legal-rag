"""
Tests for structure-aware BNSS narrative ingestion and greedy atom-packing chunker.
Asserts chapter title cleanup, atomic section packing, proviso attachment,
and absence of orphaned micro-chunks.
"""

import pytest
import os
from app.ingestion.bns_chunker import (
    fix_chapter_title_artifact,
    clean_page_text,
    extract_cross_references,
    extract_pages,
    parse_chapters_and_sections,
    MAX_CHUNK_SIZE
)

PDF_PATH = "data/raw/bns_bare_act_2023.pdf"


def test_chapter_title_artifact_fix():
    """Asserts that stray spaces in chapter titles are repaired without mangling clean titles."""
    assert fix_chapter_title_artifact("C ONSTITUTION OF CRIMINAL COURTS AND OFFICES") == "CONSTITUTION OF CRIMINAL COURTS AND OFFICES"
    assert fix_chapter_title_artifact("P OWER OF COURTS") == "POWER OF COURTS"
    assert fix_chapter_title_artifact("J URISDICTION OF THE CRIMINAL COURTS IN INQUIRIES AND TRIALS") == "JURISDICTION OF THE CRIMINAL COURTS IN INQUIRIES AND TRIALS"
    assert fix_chapter_title_artifact("ARREST OF PERSONS") == "ARREST OF PERSONS"
    assert fix_chapter_title_artifact("PRELIMINARY") == "PRELIMINARY"


def test_section_is_atomic_unit():
    """Asserts that a section under MAX_CHUNK_SIZE (1200 chars) is not split regardless of subsections."""
    pages = extract_pages(PDF_PATH, start_page=1, end_page=5)
    chunks = parse_chapters_and_sections(pages)

    # Section 1 is ~900 chars with 3 subsections - must remain 1 chunk
    sec1_chunks = [c for c in chunks if c["section_number"] == "1"]
    assert len(sec1_chunks) == 1
    assert sec1_chunks[0]["chunk_id"] == "bnss-s1-001"
    assert "Short title" in sec1_chunks[0]["text"] or "This Act may be called" in sec1_chunks[0]["text"]


def test_proviso_attached_to_parent():
    """
    Asserts that provisos are never orphaned:
    1. Chapter II Section 11 proviso is attached to parent Section 11 text.
    2. Chapter V Section 35 produces <= 6 chunks and attaches the subsection (1) proviso
       to the same chunk containing 'who commits, in the presence of a police officer, a cognizable offence'.
    """
    # 1. Section 11 check (Page ~6-8)
    pages_ch2 = extract_pages(PDF_PATH, start_page=5, end_page=10)
    chunks_ch2 = parse_chapters_and_sections(pages_ch2)
    sec11_chunks = [c for c in chunks_ch2 if c["section_number"] == "11"]

    assert len(sec11_chunks) >= 1
    proviso_chunks_11 = [c for c in sec11_chunks if c["has_proviso"]]
    assert len(proviso_chunks_11) >= 1
    for pc in proviso_chunks_11:
        assert "Provided that" in pc["text"]

    # 2. Section 35 check (Pages 13-16)
    pages_ch5 = extract_pages(PDF_PATH, start_page=13, end_page=22)
    chunks_ch5 = parse_chapters_and_sections(pages_ch5)
    sec35_chunks = [c for c in chunks_ch5 if c["section_number"] == "35"]

    print(f"\n[Test Result] Section 35 Chunks Count: {len(sec35_chunks)}")
    assert len(sec35_chunks) <= 6

    # Verify that the proviso is in the SAME chunk as 'who commits, in the presence of a police officer'
    proviso_phrase = "Provided that a police officer shall, in all cases where the arrest of a person is not required"
    parent_clause_phrase = "who commits, in the presence of a police officer, a cognizable offence"

    import re as _re
    matching_chunks = [
        c for c in sec35_chunks
        if proviso_phrase in _re.sub(r"\s+", " ", c["text"])
        and parent_clause_phrase in _re.sub(r"\s+", " ", c["text"])
    ]
    assert len(matching_chunks) >= 1, (
        "Expected Section 35 proviso to be attached in the same chunk as parent clause '(a) who commits...'"
    )


def test_no_orphaned_micro_chunks():
    """
    Parses all of Chapter V (Sections 35-62, pages ~13-25) and asserts that
    no emitted chunk has text shorter than 80 chars unless it is the entire
    content of a genuinely short section.
    """
    pages_ch5 = extract_pages(PDF_PATH, start_page=13, end_page=25)
    chunks_ch5 = parse_chapters_and_sections(pages_ch5)

    short_chunks = []
    for c in chunks_ch5:
        if len(c["text"]) < 80:
            # Check if this chunk is the ONLY chunk for that section
            sec_chunks = [x for x in chunks_ch5 if x["section_number"] == c["section_number"]]
            if len(sec_chunks) > 1:
                short_chunks.append((c["chunk_id"], len(c["text"]), c["text"]))

    print(f"\n[Test Result] Orphaned micro-chunks found in Chapter V: {len(short_chunks)}")
    for sc in short_chunks:
        print(f"  Micro-chunk: {sc[0]} (len={sc[1]}): {repr(sc[2])}")

    assert len(short_chunks) == 0, f"Found {len(short_chunks)} orphaned micro-chunks in Chapter V: {short_chunks}"


def test_running_header_stripped():
    """Asserts that gazette running headers and bare page numbers are removed."""
    raw_sample = "14\nTHE GAZETTE OF INDIA EXTRAORDINARY [Part II—\n35. (1) Any police officer may...\n__________"
    cleaned = clean_page_text(raw_sample)

    assert "THE GAZETTE OF INDIA EXTRAORDINARY" not in cleaned
    assert "__________" not in cleaned
    assert "35. (1) Any police officer may..." in cleaned


def test_cross_reference_detection():
    """Asserts detection of legal references in statute text."""
    sample_text = "Subject to the provisions of section 39 and section 35(3), or sections 103 to 105."
    refs = extract_cross_references(sample_text)

    assert any("section 39" in r.lower() for r in refs)
    assert any("section 35(3)" in r.lower() for r in refs)


def test_full_ingestion_row_count():
    """
    Parses all 157 narrative pages with greedy atom-packing.
    Asserts total chunk count is within 400-1000 range (regression guard against old 1605 count).
    """
    pages = extract_pages(PDF_PATH, start_page=1, end_page=157)
    chunks = parse_chapters_and_sections(pages)

    total_chunks = len(chunks)
    print(f"\n[Test Result] Total Chunks Parsed with Greedy Atom-Packing: {total_chunks}")

    # Sanity-bound total count (regression guard: must be below 1000)
    assert 400 <= total_chunks <= 1000

    # Ensure zero chunks have null or empty section_number
    missing_sec = [c for c in chunks if not c.get("section_number")]
    assert len(missing_sec) == 0, f"Found chunks with missing section_number: {missing_sec}"
