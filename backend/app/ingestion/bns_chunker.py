"""
Structure-aware legal parser and chunker for narrative BNSS text (pages 1-157).
Extracts chapters, sections, sub-sections, provisos, illustrations, explanations, and cross-references.
"""

import re
from typing import List, Dict, Any, Tuple, Optional
import pdfplumber

# Maximum character threshold for a single section chunk before splitting
MAX_CHUNK_SIZE = 1200

# Constants for statute metadata
ACT_NAME = "Bharatiya Nagarik Suraksha Sanhita, 2023"
ACT_SHORT = "BNSS"
DEFAULT_SOURCE_URI = "data/raw/bns_bare_act_2023.pdf"

# Words that indicate a line is referring to a section rather than defining one
NON_SECTION_PREFIXES = {
    "section", "sections", "under", "of", "in", "by", "or", "and", "to", "see",
    "sub-section", "sub-sections", "pursuant to", "refers to", "with"
}


def fix_chapter_title_artifact(title: str) -> str:
    """
    Fixes PDF-extraction artifact where a stray space is inserted after the
    first letter of the first word in a chapter title.
    E.g., 'C ONSTITUTION OF CRIMINAL COURTS AND OFFICES' -> 'CONSTITUTION OF CRIMINAL COURTS AND OFFICES'
          'P OWER OF COURTS' -> 'POWER OF COURTS'
          'J URISDICTION OF THE...' -> 'JURISDICTION OF THE...'
    Does NOT mangle clean titles like 'ARREST OF PERSONS'.
    """
    if not title:
        return ""
    title = title.strip()
    return re.sub(r"^([A-Z])\s([A-Z]{2,})", r"\1\2", title)


def clean_page_text(text: str) -> str:
    """
    Cleans raw page text from PDF:
    - Strips bare page-number headers/footers
    - Strips Gazette header noise (e.g. THE GAZETTE OF INDIA EXTRAORDINARY, Part II, etc.)
    - Dehyphenates words broken across line breaks
    - Preserves section and paragraph breaks
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for i, line in enumerate(lines):
        line_str = line.strip()

        # Strip top or bottom bare page number lines (e.g. "155" or "2")
        if (i < 3 or i >= len(lines) - 2) and re.match(r"^\d{1,3}$", line_str):
            continue

        # Strip Gazette running header/footer noise lines
        if any(noise in line_str for noise in [
            "THE GAZETTE OF INDIA EXTRAORDINARY",
            "REGISTERED NO.",
            "MINISTRY OF LAW AND JUSTICE",
            "PUBLISHED BY AUTHORITY",
            "Separate paging is given",
            "EXTRAORDINARY",
            "[Part II—",
            "[Part II-",
            "Sec. 1]",
            "PART II—Section 1",
            "PART II-Section 1"
        ]):
            continue

        # Strip separator lines (__________)
        if re.match(r"^_{4,}$", line_str):
            continue

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)

    # Dehyphenate words split across line breaks (e.g. "investi-\ngation" -> "investigation")
    cleaned_text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", cleaned_text)

    return cleaned_text


def extract_pages(pdf_path: str, start_page: int = 1, end_page: int = 157) -> List[Tuple[int, str]]:
    """
    Extracts raw text per page from PDF between start_page and end_page (1-indexed, inclusive).
    Returns list of tuples: (page_number, raw_text).
    """
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        actual_end = min(end_page, total_pages)
        for idx in range(start_page - 1, actual_end):
            page_num = idx + 1
            raw_text = pdf.pages[idx].extract_text() or ""
            pages_text.append((page_num, raw_text))
    return pages_text


def extract_cross_references(text: str) -> List[str]:
    """
    Detects legal cross-references in text after line-rejoining & dehyphenation.
    E.g. 'section 2', 'section 35(3)', 'sections 103 to 105', 'sub-section (1) of section 187'.
    """
    if not text:
        return []

    pattern = re.compile(
        r"\b(?:sections?|sub-section)\s+\d+(?:\(\d+\))?(?:\([a-z]\))?(?:\s*(?:to|and|,)\s*\d+(?:\(\d+\))?)?",
        re.IGNORECASE
    )

    matches = []
    for match in pattern.finditer(text):
        ref = match.group(0).strip()
        if ref and ref not in matches:
            matches.append(ref)
    return matches


def parse_chapters_and_sections(
    pages_text: List[Tuple[int, str]],
    source_uri: str = DEFAULT_SOURCE_URI
) -> List[Dict[str, Any]]:
    """
    Walks cleaned text of pages 1-157 and yields structured StatuteChunk dictionaries.
    Preserves legal structure, provisos, explanations, illustrations, and metadata.
    """
    chunks: List[Dict[str, Any]] = []

    current_chapter: Optional[str] = None
    current_chapter_title: Optional[str] = None
    needs_review_chapter: bool = False

    doc_lines: List[Tuple[int, str]] = []

    for page_num, raw_text in pages_text:
        cleaned = clean_page_text(raw_text)
        for line in cleaned.split("\n"):
            doc_lines.append((page_num, line))

    chapter_header_re = re.compile(r"^CHAPTER\s+([IVXLCDM]+)\s*(.*)", re.IGNORECASE)
    section_start_re = re.compile(r"^(.*?)\b(\d{1,3})\.\s*(.*)")

    section_blocks: List[Dict[str, Any]] = []
    current_block: Optional[Dict[str, Any]] = None

    idx = 0
    while idx < len(doc_lines):
        page_num, line = doc_lines[idx]
        line_trimmed = line.strip()

        # Check for Chapter Header
        chap_match = chapter_header_re.match(line_trimmed)
        if chap_match:
            current_chapter = chap_match.group(1).upper()
            raw_title = chap_match.group(2).strip()

            if not raw_title and idx + 1 < len(doc_lines):
                next_page, next_line = doc_lines[idx + 1]
                if next_line.strip() and not next_line.strip().startswith("CHAPTER"):
                    raw_title = next_line.strip()
                    idx += 1

            current_chapter_title = fix_chapter_title_artifact(raw_title)
            needs_review_chapter = bool(re.search(r"\b[A-Z]\s[A-Z]\b", current_chapter_title))

            idx += 1
            continue

        # Check for Section Start
        sec_match = section_start_re.match(line_trimmed)
        if sec_match:
            prefix = sec_match.group(1).strip()
            sec_num_str = sec_match.group(2)
            body_start = sec_match.group(3).strip()

            sec_val = int(sec_num_str)
            if 1 <= sec_val <= 531:
                prefix_words = prefix.lower().split()
                last_prefix_word = prefix_words[-1] if prefix_words else ""

                if len(prefix) < 60 and last_prefix_word not in NON_SECTION_PREFIXES:
                    sec_title = prefix if (prefix and not prefix.endswith(".")) else f"Section {sec_num_str}"
                    if prefix.endswith("."):
                        sec_title = prefix[:-1]

                    if current_block:
                        section_blocks.append(current_block)

                    line_content = f"{sec_num_str}. {body_start}" if body_start else f"{sec_num_str}."
                    current_block = {
                        "act": ACT_NAME,
                        "act_short": ACT_SHORT,
                        "chapter": current_chapter,
                        "chapter_title": current_chapter_title,
                        "section_number": sec_num_str,
                        "section_title": sec_title,
                        "lines": [(page_num, line_content)],
                        "page_start": page_num,
                        "page_end": page_num,
                        "needs_review": needs_review_chapter
                    }
                    idx += 1
                    continue

        if current_block:
            current_block["lines"].append((page_num, line))
            current_block["page_end"] = page_num

        idx += 1

    if current_block:
        section_blocks.append(current_block)

    # Dictionary tracking sequence numbers per section_number across the whole run
    global_section_seq: Dict[str, int] = {}

    # Process section blocks into chunks with atomic / splitting logic
    for block in section_blocks:
        sec_num = block["section_number"]
        block_lines = block["lines"]

        page_start = block["page_start"]
        page_end = block["page_end"]

        full_block_text = "\n".join([l[1] for l in block_lines]).strip()
        full_block_text = re.sub(r"\n{3,}", "\n\n", full_block_text)

        has_proviso = any(p in full_block_text for p in ["Provided that", "Provided further that", "Provided also that"])
        has_explanation = "Explanation" in full_block_text
        has_illustration = "Illustration" in full_block_text
        has_exception = "Exception" in full_block_text

        refs = extract_cross_references(full_block_text)

        if len(full_block_text) <= MAX_CHUNK_SIZE:
            seq = global_section_seq.get(sec_num, 0) + 1
            global_section_seq[sec_num] = seq
            chunk_id = f"bnss-s{sec_num}-{seq:03d}"

            sub_match = re.search(r"^\d+\.\s*(\(\d+\))", full_block_text)
            subsection = sub_match.group(1) if sub_match else None

            chunks.append({
                "act": block["act"],
                "act_short": block["act_short"],
                "chapter": block["chapter"],
                "chapter_title": block["chapter_title"],
                "section_number": sec_num,
                "section_title": block["section_title"],
                "subsection": subsection,
                "clause": None,
                "text": full_block_text,
                "has_illustration": has_illustration,
                "has_proviso": has_proviso,
                "has_exception": has_exception,
                "page_start": page_start,
                "page_end": page_end,
                "chunk_id": chunk_id,
                "source_uri": source_uri,
                "references_json": refs,
                "needs_review": block["needs_review"]
            })
        else:
            sub_sections = re.split(r"\n(?=\(\d+\)|\([a-z]\)|Provided that|Explanation)", full_block_text)

            for sub_text in sub_sections:
                sub_text_trimmed = sub_text.strip()
                if not sub_text_trimmed:
                    continue

                seq = global_section_seq.get(sec_num, 0) + 1
                global_section_seq[sec_num] = seq
                chunk_id = f"bnss-s{sec_num}-{seq:03d}"

                sub_match = re.search(r"^(\(\d+\)|\([a-z]\))", sub_text_trimmed)
                subsection = sub_match.group(1) if sub_match else None

                sub_has_proviso = any(p in sub_text_trimmed for p in ["Provided that", "Provided further that"])
                sub_has_explanation = "Explanation" in sub_text_trimmed
                sub_has_illustration = "Illustration" in sub_text_trimmed
                sub_refs = extract_cross_references(sub_text_trimmed)

                chunks.append({
                    "act": block["act"],
                    "act_short": block["act_short"],
                    "chapter": block["chapter"],
                    "chapter_title": block["chapter_title"],
                    "section_number": sec_num,
                    "section_title": block["section_title"],
                    "subsection": subsection,
                    "clause": None,
                    "text": sub_text_trimmed,
                    "has_illustration": sub_has_illustration,
                    "has_proviso": sub_has_proviso,
                    "has_exception": has_exception,
                    "page_start": page_start,
                    "page_end": page_end,
                    "chunk_id": chunk_id,
                    "source_uri": source_uri,
                    "references_json": sub_refs,
                    "needs_review": block["needs_review"]
                })

    return chunks
