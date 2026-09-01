"""
Tests for structure-aware BNSS narrative ingestion and greedy atom-packing chunker.
Asserts chapter title cleanup, atomic section packing, proviso attachment,
absence of orphaned micro-chunks, chapter title consistency across corpus,
token limits for definitions, recovery of sections 104/105, and monotonic section sequence.
"""

import re

from app.ingestion.bns_chunker import (
    clean_page_text,
    extract_cross_references,
    extract_pages,
    fix_chapter_title_artifact,
    parse_chapters_and_sections,
)
from app.retrieval.embeddings import get_embedding_model

PDF_PATH = "data/raw/bns_bare_act_2023.pdf"


def test_chapter_title_artifact_fix():
    """Asserts that stray spaces in chapter titles are repaired without mangling clean titles."""
    assert (
        fix_chapter_title_artifact("C ONSTITUTION OF CRIMINAL COURTS AND OFFICES")
        == "CONSTITUTION OF CRIMINAL COURTS AND OFFICES"
    )
    assert fix_chapter_title_artifact("P OWER OF COURTS") == "POWER OF COURTS"
    assert (
        fix_chapter_title_artifact(
            "J URISDICTION OF THE CRIMINAL COURTS IN INQUIRIES AND TRIALS"
        )
        == "JURISDICTION OF THE CRIMINAL COURTS IN INQUIRIES AND TRIALS"
    )
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
    assert (
        "Short title" in sec1_chunks[0]["text"]
        or "This Act may be called" in sec1_chunks[0]["text"]
    )


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
    parent_clause_phrase = (
        "who commits, in the presence of a police officer, a cognizable offence"
    )

    matching_chunks = [
        c
        for c in sec35_chunks
        if proviso_phrase in re.sub(r"\s+", " ", c["text"])
        and parent_clause_phrase in re.sub(r"\s+", " ", c["text"])
    ]
    assert (
        len(matching_chunks) >= 1
    ), "Expected Section 35 proviso to be attached in the same chunk as parent clause '(a) who commits...'"


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
            sec_chunks = [
                x for x in chunks_ch5 if x["section_number"] == c["section_number"]
            ]
            if len(sec_chunks) > 1:
                short_chunks.append((c["chunk_id"], len(c["text"]), c["text"]))

    print(
        f"\n[Test Result] Orphaned micro-chunks found in Chapter V: {len(short_chunks)}"
    )
    for sc in short_chunks:
        print(f"  Micro-chunk: {sc[0]} (len={sc[1]}): {repr(sc[2])}")

    assert (
        len(short_chunks) == 0
    ), f"Found {len(short_chunks)} orphaned micro-chunks in Chapter V: {short_chunks}"


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
    Asserts total chunk count is within 400-1000 range.
    """
    pages = extract_pages(PDF_PATH, start_page=1, end_page=157)
    chunks = parse_chapters_and_sections(pages)

    total_chunks = len(chunks)
    print(
        f"\n[Test Result] Total Chunks Parsed with Greedy Atom-Packing: {total_chunks}"
    )

    # Sanity-bound total count
    assert 400 <= total_chunks <= 1000

    # Ensure zero chunks have null or empty section_number
    missing_sec = [c for c in chunks if not c.get("section_number")]
    assert (
        len(missing_sec) == 0
    ), f"Found chunks with missing section_number: {missing_sec}"


def test_no_chapter_title_corruption():
    """
    Parses ALL 157 pages and verifies corpus-wide chapter consistency:
    (a) Total number of DISTINCT chapters found is between 35-45 (BNSS has exactly 39 chapters).
    (b) For every distinct (chapter, chapter_title) pair, chapter_title is entirely uppercase.
    (c) Specifically asserts verified ground truths:
        - Chapter X contains 'MAINTENANCE'
        - Chapter XI contains 'PUBLIC ORDER'
        - Chapter XXV contains 'EVIDENCE'
        - Chapter XXVI contains 'GENERAL PROVISIONS AS TO INQUIRIES AND TRIALS'
    """
    pages = extract_pages(PDF_PATH, start_page=1, end_page=157)
    chunks = parse_chapters_and_sections(pages)

    distinct_chapters = {}
    for c in chunks:
        chap = c.get("chapter")
        title = c.get("chapter_title")
        if chap and chap not in distinct_chapters:
            distinct_chapters[chap] = title

    print(f"\n[Test Result] Distinct Chapters count: {len(distinct_chapters)}")
    for num, title in distinct_chapters.items():
        print(f"  Chapter {num:6s} -> '{title}'")

    # (a) Sanity bound: 35-45 chapters
    assert (
        35 <= len(distinct_chapters) <= 45
    ), f"Expected 35-45 chapters, found {len(distinct_chapters)}"

    # (b) Every chapter title must be entirely uppercase
    for num, title in distinct_chapters.items():
        assert title is not None and len(title) > 0, f"Chapter {num} has empty title"
        letters_only = re.sub(r"[^A-Za-z]", "", title)
        assert (
            letters_only.isupper()
        ), f"Corrupted chapter title found for Chapter {num}: '{title}'"

    # (c) Specific ground truth checks
    assert "X" in distinct_chapters
    assert "MAINTENANCE" in distinct_chapters["X"]

    assert "XI" in distinct_chapters
    assert "PUBLIC ORDER" in distinct_chapters["XI"]

    assert "XXV" in distinct_chapters
    assert "EVIDENCE" in distinct_chapters["XXV"]

    assert "XXVI" in distinct_chapters
    assert "GENERAL PROVISIONS" in distinct_chapters["XXVI"]


def test_definitions_section_under_token_limit():
    """
    Parses Chapter I (pages 1-5), finds all chunks for Section 2 ('Definitions'),
    tokenizes each chunk with the real BAAI/bge-base-en-v1.5 model tokenizer,
    and asserts EVERY chunk is strictly under 512 tokens.
    """
    model = get_embedding_model()
    pages = extract_pages(PDF_PATH, start_page=1, end_page=5)
    chunks = parse_chapters_and_sections(pages)

    sec2_chunks = [c for c in chunks if c["section_number"] == "2"]
    print(
        f"\n[Test Result] Section 2 Chunks Count after Tier-2 Generic Splitting: {len(sec2_chunks)}"
    )
    assert (
        len(sec2_chunks) >= 4
    ), f"Expected Section 2 to be split into multiple chunks, got {len(sec2_chunks)}"

    for i, c in enumerate(sec2_chunks):
        prefixed_text = f"passage: {c['text']}"
        tokens = model.tokenizer(prefixed_text)["input_ids"]
        token_count = len(tokens)
        print(
            f"  Sec 2 Chunk {i+1} ({c['chunk_id']}): {len(c['text'])} chars, {token_count} tokens"
        )
        assert (
            token_count <= 512
        ), f"Section 2 chunk {c['chunk_id']} has {token_count} tokens, which exceeds max_seq_length (512)"


def test_section_104_105_not_swallowed():
    """
    Asserts that sections 104 and 105 are recovered as distinct standalone chunks
    and are not swallowed into section 103.
    """
    pages = extract_pages(PDF_PATH, start_page=28, end_page=33)
    chunks = parse_chapters_and_sections(pages)

    sec103_chunks = [c for c in chunks if c["section_number"] == "103"]
    sec104_chunks = [c for c in chunks if c["section_number"] == "104"]
    sec105_chunks = [c for c in chunks if c["section_number"] == "105"]
    sec106_chunks = [c for c in chunks if c["section_number"] == "106"]

    assert len(sec104_chunks) >= 1, "Expected section 104 to exist as its own chunk"
    assert len(sec105_chunks) >= 1, "Expected section 105 to exist as its own chunk"
    assert len(sec106_chunks) >= 1, "Expected section 106 to exist as its own chunk"

    # Section 103 chunks must NOT contain Section 104 header text
    for c in sec103_chunks:
        assert "104. When, in the execution" not in c["text"]
        assert "105. The process of conducting" not in c["text"]

    # Section 104 chunk content verification
    assert "When, in the execution of a search-warrant" in sec104_chunks[0]["text"]

    # Section 105 chunk content verification
    assert "The process of conducting search of a place" in sec105_chunks[0]["text"]


def test_no_backward_section_regression():
    """
    Walks the full parsed corpus and asserts that section numbers are monotonically
    non-decreasing from 1 to 531 with 0 missing integer gaps.
    """
    pages = extract_pages(PDF_PATH, start_page=1, end_page=157)
    chunks = parse_chapters_and_sections(pages)

    seen_sections = []
    last_sec = 0
    for c in chunks:
        sec_num = int(c["section_number"])
        if sec_num != last_sec:
            assert (
                sec_num > last_sec
            ), f"Backward section regression detected: {sec_num} after {last_sec}"
            seen_sections.append(sec_num)
            last_sec = sec_num

    print(f"\n[Test Result] Total Distinct Sections Parsed: {len(seen_sections)}")
    assert min(seen_sections) == 1
    assert max(seen_sections) == 531

    expected_range = set(range(1, 532))
    missing_gaps = sorted(list(expected_range - set(seen_sections)))
    assert (
        len(missing_gaps) == 0
    ), f"Found missing section gaps in corpus: {missing_gaps}"
